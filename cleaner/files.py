"""Inventory and explicit, reviewed cleanup of known disposable Codex files."""
from __future__ import annotations

import ctypes
import codecs
import json
import os
from pathlib import Path
import re
import subprocess
import stat as stat_types
from bisect import bisect_left
import threading
import time
import uuid

from .activity import probe_file

IMAGE_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
               '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp', '.ico': 'image/x-icon'}
TEXT_LIMIT = 256 * 1024
IMAGE_LIMIT = 16 * 1024 * 1024


def preview_kind(name):
    suffix = Path(name).suffix.lower()
    if suffix in IMAGE_TYPES: return 'image'
    if suffix in ('.exe', '.dll', '.sqlite', '.db', '.zip', '.pdf', '.woff', '.woff2', '.bin', '.7z', '.gz'):
        return 'unsupported'
    return 'text'


def normal_path(value):
    value = str(value)
    if value.startswith('\\\\?\\'):
        value = '\\\\' + value[8:] if value.startswith('\\\\?\\UNC\\') else value[4:]
    return Path(value).expanduser().resolve()


def linked(path):
    stat = path.lstat()
    return path.is_symlink() or bool(getattr(stat, 'st_file_attributes', 0) & 0x400)


def identity(stat):
    # Recent Windows Python versions may expose creation time in stat().ctime,
    # but metadata change time in fstat().ctime. Compare creation time explicitly.
    created = getattr(stat, 'st_birthtime_ns', stat.st_ctime_ns)
    return (stat.st_size, stat.st_mtime_ns, created, stat.st_dev, stat.st_ino, stat.st_nlink)


def safe_path(home, relative):
    path = home / relative
    if path == home or path.resolve() == home or not path.resolve().is_relative_to(home):
        raise ValueError('Unsafe cleanup path')
    for part in (path, *path.parents):
        if part == home:
            break
        if linked(part):
            raise ValueError('Links and junctions cannot be cleaned')
    return path


def delete_file(home, relative, expected):
    """On Windows, delete the checked handle; reject writers and path changes."""
    path = safe_path(home, relative)
    if os.name != 'nt':
        if identity(path.stat()) != expected or expected[-1] != 1:
            raise ValueError('File changed; scan again')
        path.unlink()
        return
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # READ + DELETE, sharing only reads: active writers/deleters cannot coexist.
    handle = kernel.CreateFileW(str(path), 0x80010000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    fd = None
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
        buffer = ctypes.create_unicode_buffer(32768)
        length = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        final = buffer.value
        if final.startswith('\\\\?\\UNC\\'):
            final = '\\\\' + final[8:]
        elif final.startswith('\\\\?\\'):
            final = final[4:]
        if Path(final).resolve() != path.resolve() or not Path(final).resolve().is_relative_to(home):
            raise ValueError('File moved outside its cleanup path')
        if identity(os.fstat(fd)) != expected or expected[-1] != 1:
            raise ValueError('File changed; scan again')
        disposition = ctypes.c_bool(True)
        if not kernel.SetFileInformationByHandle(handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)):
            error = ctypes.get_last_error()
            if error != 5: raise ctypes.WinError(error)
            # Git pack objects are commonly read-only. Delete the same checked
            # handle with IGNORE_READONLY_ATTRIBUTE, without changing attributes
            # or using POSIX semantics to bypass existing open handles.
            flags = wintypes.DWORD(0x1 | 0x4 | 0x10)
            if not kernel.SetFileInformationByHandle(handle, 21, ctypes.byref(flags), ctypes.sizeof(flags)):
                extended_error = ctypes.get_last_error()
                raise ctypes.WinError(error if extended_error in (1, 50, 87) else extended_error)
    finally:
        if fd is not None:
            os.close(fd)
        else:
            kernel.CloseHandle(handle)


def read_preview(home, relative, expected, limit):
    """Read only the listed file, with bounded memory and checked identity."""
    path = safe_path(home, relative)
    if expected[-1] != 1: raise ValueError('Links and junctions cannot be cleaned')
    if os.name == 'nt':
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
            if (not length or length >= len(buffer) or normal_path(buffer.value) != path.resolve()
                    or not normal_path(buffer.value).is_relative_to(home)):
                raise ValueError('Unsafe cleanup path')
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
        except Exception:
            kernel.CloseHandle(handle); raise
        stream = os.fdopen(fd, 'rb')
    else:
        stream = path.open('rb')
    with stream:
        if identity(os.fstat(stream.fileno())) != expected: raise ValueError('File changed; scan again')
        data = stream.read(limit)
        if identity(os.fstat(stream.fileno())) != expected: raise ValueError('File changed; scan again')
        return data


class FileCleanup:
    def __init__(self, store):
        self.store = store
        self.plans = {}
        self.stop = threading.Event()
        self.progress = {'running': False, 'done': 0, 'total': 0, 'results': []}
        self.scan_lock = threading.Lock()
        self.browse_lock = threading.Lock()
        self.previews = {}
        self.listings = {}

    def _inventory_steps(self, home):
        manifest, issues = {}, set()
        with os.scandir(home) as iterator: roots = list(iterator)
        priority = {name: index for index, name in enumerate(('.sandbox', 'visualizations', 'generated_images',
                    'cache', '.tmp', 'attachments', 'plans', 'tmp', 'plugins'))}
        roots.sort(key=lambda root: (priority.get(root.name, 99), root.name.lower()))
        folders = []
        for root in roots:
            try:
                if root.is_dir(follow_symlinks=False): folders.append({'name': root.name, 'bytes': 0, 'files': 0, 'issues': 0, 'pending': True})
            except OSError: pass
        by_name = {folder['name']: folder for folder in folders}
        scan = {'files': 0, 'bytes': 0, 'path': '', 'done': 0, 'total': len(roots)}
        last = time.monotonic()
        yield manifest, issues, folders, dict(scan), False
        for root in roots:
            size = count = failures = 0
            stack = [root]
            scan['path'] = root.name
            while stack:
                item = stack.pop()
                relative = Path(item.path).relative_to(home).as_posix()
                try:
                    info = item.stat(follow_symlinks=False)
                    if item.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                        issues.add(relative); failures += 1
                    elif stat_types.S_ISDIR(info.st_mode):
                        with os.scandir(item.path) as iterator: stack.extend(iterator)
                    elif stat_types.S_ISREG(info.st_mode):
                        # Windows DirEntry metadata omits inode/link identity. Fetch it
                        # once for files so preview and deletion retain their checks.
                        if os.name == 'nt': info = os.stat(item.path, follow_symlinks=False)
                        manifest[relative] = identity(info)
                        size += info.st_size; count += 1
                        scan['files'] += 1; scan['bytes'] += info.st_size
                        if info.st_nlink != 1:
                            issues.add(relative); failures += 1
                except OSError:
                    issues.add(relative); failures += 1
                if time.monotonic() - last >= .2:
                    if root.name in by_name: by_name[root.name].update(bytes=size, files=count, issues=failures)
                    yield manifest, issues, folders, dict(scan), False
                    last = time.monotonic()
            if root.name in by_name: by_name[root.name].update(bytes=size, files=count, issues=failures, pending=False)
            scan['done'] += 1
            yield manifest, issues, folders, dict(scan), True

    def _inventory(self, home):
        for manifest, issues, folders, _, _ in self._inventory_steps(home): pass
        return manifest, issues, folders

    def _references(self, home):
        references = set()
        reliable = True
        def visit(value):
            if isinstance(value, dict):
                for child in value.values(): visit(child)
            elif isinstance(value, list):
                for child in value: visit(child)
            elif isinstance(value, str) and len(value) < 4096:
                try:
                    path = Path(value).expanduser()
                    if not path.is_absolute(): return
                    resolved = normal_path(path)
                    if resolved != home and resolved.is_relative_to(home):
                        references.add(resolved)
                except (OSError, ValueError): pass
        def visit_routes(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key.startswith('thread-tab-routes-v1:'):
                        visit(child)
                    else:
                        visit_routes(child)
        for name in ('config.toml', '.codex-global-state.json'):
            path = home / name
            if not path.exists(): continue
            try:
                text = path.read_text(encoding='utf-8')
                if name.endswith('.json'):
                    # Past permission grants and writable-root lists are not open-file references.
                    visit_routes(json.loads(text))
                else:
                    try:
                        import tomllib
                        visit(tomllib.loads(text))
                    except ImportError:
                        # Python 3.10: retain temp/cache directories if TOML cannot be parsed.
                        reliable = False
            except (OSError, ValueError): reliable = False
        return references, reliable

    def _scan(self, days, inventory=None):
        if days not in (7, 30, 90): raise ValueError('Unsupported retention period')
        home = normal_path(self.store.home)
        manifest, issues, folders = self._inventory(home) if inventory is None else inventory
        names = sorted(manifest)
        references, reliable = self._references(home)
        cutoff = time.time() - days * 86400
        entries, members = [], {}
        staging_busy = any(probe_file(home / name) in ('busy', 'unknown') for name in manifest
                           if name.startswith('.tmp/') and name.count('/') == 1 and name.endswith('.lock'))
        active = {sid for sid in self.store.current if sid}
        try:
            for lock in (home / 'thread-writer-locks').glob('*.lock'):
                if probe_file(lock) in ('busy', 'unknown'): active.add(lock.stem)
        except OSError: pass
        def add(relative, reason, recommend=False, retention=True, runtime=False):
            if relative in manifest:
                paths = {relative: manifest[relative]} if not relative.endswith('.lock') else {}
            else:
                prefix = relative + '/'
                paths = {}
                index = bisect_left(names, prefix)
                while index < len(names) and names[index].startswith(prefix):
                    name = names[index]
                    if not name.endswith('.lock'): paths[name] = manifest[name]
                    index += 1
            if not paths: return
            target = home / relative
            problem = ''
            if any(name == relative or name.startswith(relative + '/') for name in issues): problem = 'unsafe'
            elif any(target == ref or target in ref.parents or ref in target.parents for ref in references): problem = 'referenced'
            elif any(sid in Path(relative).parts for sid in active): problem = 'active'
            elif runtime: problem = 'current_runtime'
            elif relative.startswith('.tmp/') and staging_busy: problem = 'active'
            elif reason in ('temporary', 'cache') and not reliable: problem = 'references_unknown'
            elif retention and max(stat[1] for stat in paths.values()) / 1e9 >= cutoff: problem = 'recent'
            # Arg0 directories are coordinated by lock files, even when their scripts look stale.
            if relative.startswith('tmp/arg0/'):
                for name in manifest:
                    if name.startswith(relative + '/') and name.endswith('.lock') and probe_file(home / name) in ('busy', 'unknown'):
                        problem = 'active'
            entry = {'id': relative, 'name': relative, 'category': relative.split('/')[0],
                     'bytes': sum(stat[0] for stat in paths.values()), 'files': len(paths),
                     'modified': max(stat[1] for stat in paths.values()) / 1e9,
                     'allowed': not problem, 'recommended': recommend and not problem,
                     'reason': problem or reason, 'samples': list(paths)[:6]}
            entries.append(entry); members[relative] = paths
        # Logs and failed atomic state writes are disposable; config/state files are retained.
        for name in manifest:
            if re.fullmatch(r'\.sandbox/sandbox\.\d{4}-\d{2}-\d{2}\.log', name): add(name, 'old_log', True)
            elif re.fullmatch(r'\.\.codex-global-state\.json(?:\.bak)?\.tmp-[^/]+', name): add(name, 'temporary', True)
            elif '/' not in name and name.startswith('config.toml.bak'): add(name, 'backup', retention=False)
            elif name.startswith('ambient-suggestions/') and name.endswith('.json'): add(name, 'cache', True)
        runners = sorted((name for name in manifest if re.fullmatch(r'\.sandbox-bin/codex-command-runner-[^/]+\.exe', name)),
                         key=lambda name: manifest[name][1], reverse=True)
        version = self.store.cli.get('version', '').removeprefix('codex-cli ')
        for name in runners:
            add(name, 'old_runner', True, runtime=name in runners[:2] or Path(name).name == f'codex-command-runner-{version}.exe')
        # Only known staging directories are candidates; installed plugins remain managed by Codex.
        for parent in ('.tmp', 'plugins/.remote-plugin-install-staging', 'tmp/arg0'):
            directory = home / parent
            if not directory.is_dir() or linked(directory): continue
            for child in directory.iterdir():
                if not child.is_dir() or linked(child): continue
                if parent == '.tmp' and child.name not in ('plugins', 'marketplaces', 'legacy-primary-runtime-skills', 'bundled-marketplaces'): continue
                if child.name == 'bundled-marketplaces':
                    for market in child.iterdir():
                        if market.is_dir(): add(market.relative_to(home).as_posix(), 'temporary', True)
                else: add(child.relative_to(home).as_posix(), 'temporary', True)
        cache_roots = ('cache/codex_apps_server_info/', 'cache/codex_apps_tools/', 'cache/remote_plugin_catalog/',
                       'cache/computer-use/', 'cache/codex_app_directory/')
        for name in manifest:
            if name.startswith(cache_roots) and name.endswith('.json'): add(name, 'cache', True)
        # User outputs can be selected explicitly, but are never auto-recommended.
        artifacts = set()
        for name in manifest:
            parts = Path(name).parts
            if parts[0] not in ('visualizations', 'generated_images', 'attachments', 'plans'): continue
            for index, part in enumerate(parts[1:-1], 1):
                try: uuid.UUID(part)
                except ValueError: continue
                artifacts.add('/'.join(parts[:index+1])); break
        for name in sorted(artifacts): add(name, 'artifact', retention=False)
        entries.sort(key=lambda entry: (not entry['recommended'], not entry['allowed'], -entry['bytes'], entry['id']))
        report = {'home': str(self.store.home.resolve()), 'days': days, 'entries': entries, 'directories': folders,
                  'bytes': sum(stat[0] for stat in manifest.values()), 'scanned_at': time.time()}
        return report, members

    def inspect(self, days=7):
        with self.scan_lock:
            report, members = self._scan(days)
        return self._remember_listing(report, members)

    def _remember_listing(self, report, members, token=None):
        token = token or uuid.uuid4().hex
        with self.browse_lock:
            self.listings = {key: value for key, value in self.listings.items()
                             if value['home'] == report['home']}
            while token not in self.listings and len(self.listings) >= 4: self.listings.pop(next(iter(self.listings)))
            self.listings[token] = {'home': report['home'], 'days': report['days'], 'members': members}
        return {**report, 'snapshot': token}

    def iter_inspect(self, days=7):
        if days not in (7, 30, 90): raise ValueError('Unsupported retention period')
        expected_home = str(self.store.home.resolve())
        home = normal_path(self.store.home)
        token = uuid.uuid4().hex
        latest = {'home': expected_home, 'days': days, 'entries': [], 'directories': [], 'bytes': 0}
        published = sent = 0
        with self.scan_lock:
            for manifest, issues, folders, scan, finished_root in self._inventory_steps(home):
                if str(self.store.home.resolve()) != expected_home: raise ValueError('File changed; scan again')
                changed = False
                if finished_root and time.monotonic() - published >= .2:
                    latest, members = self._scan(days, (manifest, issues, folders))
                    # Display partial results without treating incomplete checks as recommendations.
                    latest['entries'] = [{**entry, 'allowed': False, 'recommended': False, 'reason': 'scanning'}
                                         for entry in latest['entries']]
                    latest = self._remember_listing(latest, members, token)
                    published = time.monotonic()
                    changed = True
                if not sent or changed or time.monotonic() - sent >= .2:
                    yield {**latest, 'bytes': scan['bytes'], 'directories': [dict(folder) for folder in folders],
                           'complete': False, 'scan': scan}
                    sent = time.monotonic()
            report, members = self._scan(days, (manifest, issues, folders))
            if str(self.store.home.resolve()) != expected_home: raise ValueError('File changed; scan again')
            report = self._remember_listing(report, members, token)
        yield {**report, 'complete': True, 'scan': {**scan, 'path': ''}}

    def _listed_members(self, days, snapshot):
        if snapshot:
            if not isinstance(snapshot, str): raise ValueError('Invalid file list request')
            with self.browse_lock:
                listing = self.listings.get(snapshot)
                if (not listing or listing['days'] != days
                        or listing['home'] != str(self.store.home.resolve())):
                    raise ValueError('文件列表已过期，请重新检查')
                return listing['home'], listing['members']
        # Compatibility for clients that request a list before an inspection.
        with self.scan_lock:
            report, members = self._scan(days)
        return report['home'], members

    def list_files(self, sid, days=7, offset=0, query='', snapshot=''):
        if not isinstance(sid, str) or not isinstance(query, str) or len(query) > 256 or not isinstance(offset, int) or offset < 0:
            raise ValueError('Invalid file list request')
        home, members = self._listed_members(days, snapshot)
        with self.browse_lock:
            if sid not in members:
                raise ValueError('Cleanup items changed or are protected; scan again')
            files = members[sid]
            now = time.time()
            self.previews = {key: value for key, value in self.previews.items()
                             if value['expires'] > now and value['home'] == home}
            while len(self.previews) >= 16: self.previews.pop(next(iter(self.previews)))
            token = uuid.uuid4().hex
            self.previews[token] = {'home': home, 'files': files, 'expires': now + 900}
        names = sorted((name for name in files if query.casefold() in name.casefold()), key=str.casefold)
        offset = min(offset, ((len(names)-1)//100)*100) if names else 0
        page = names[offset:offset+100]
        return {'id': sid, 'token': token, 'directory': str(Path(sid).parent).replace('\\', '/') if sid in files else sid,
                'total': len(files), 'matched': len(names), 'offset': offset,
                'next': offset+100 if offset+100 < len(names) else None,
                'items': [{'path': name, 'bytes': files[name][0], 'modified': files[name][1]/1e9,
                           'kind': preview_kind(name)} for name in page]}

    def _preview_target(self, token, relative):
        if not isinstance(token, str) or not isinstance(relative, str): raise ValueError('Invalid file list request')
        with self.browse_lock:
            session = self.previews.get(token)
            if not session or session['expires'] < time.time() or session['home'] != str(self.store.home.resolve()):
                raise ValueError('文件预览已过期，请重新打开文件列表')
            expected = session['files'].get(relative)
            if expected is None: raise ValueError('Unsafe cleanup path')
            home = normal_path(session['home'])
        return home, expected

    def preview(self, token, relative):
        home, expected = self._preview_target(token, relative)
        kind = preview_kind(relative)
        result = {'path': relative, 'kind': kind, 'bytes': expected[0], 'modified': expected[1]/1e9}
        if kind == 'image':
            if expected[0] > IMAGE_LIMIT: return {**result, 'kind': 'unsupported', 'reason': 'image_limit'}
            return result
        if kind == 'unsupported': return result
        raw = read_preview(home, relative, expected, TEXT_LIMIT)
        truncated = expected[0] > len(raw)
        encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
        try:
            text = codecs.getincrementaldecoder(encoding)().decode(raw, final=not truncated)
            if '\x00' in text: return {**result, 'kind': 'unsupported'}
        except UnicodeError:
            return {**result, 'kind': 'unsupported'}
        return {**result, 'text': text.replace('\r\n', '\n'), 'truncated': truncated}

    def image(self, token, relative):
        home, expected = self._preview_target(token, relative)
        if preview_kind(relative) != 'image' or expected[0] > IMAGE_LIMIT:
            raise ValueError('图片无法预览')
        raw = read_preview(home, relative, expected, IMAGE_LIMIT)
        valid = (raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff') or
                 raw.startswith((b'GIF87a', b'GIF89a', b'BM', b'\x00\x00\x01\x00')) or
                 raw.startswith(b'RIFF') and raw[8:12] == b'WEBP')
        if not valid: raise ValueError('图片无法预览')
        return raw, IMAGE_TYPES[Path(relative).suffix.lower()]

    def reveal(self, sid='', days=7, token='', relative='', snapshot=''):
        if relative:
            home, expected = self._preview_target(token, relative)
            path = safe_path(home, relative)
            if identity(path.stat()) != expected: raise ValueError('File changed; scan again')
        else:
            if not isinstance(sid, str): raise ValueError('Invalid file list request')
            home, members = self._listed_members(days, snapshot)
            if sid not in members: raise ValueError('Cleanup items changed or are protected; scan again')
            if home != str(self.store.home.resolve()): raise ValueError('File changed; scan again')
            path = safe_path(normal_path(home), sid)
        if os.name != 'nt': raise ValueError('打开文件夹仅支持 Windows')
        args = ['explorer.exe', str(path)] if path.is_dir() else ['explorer.exe', '/select,', str(path)]
        subprocess.Popen(args, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return {'ok': True}

    def plan(self, ids, days=7):
        if self.progress['running']: raise ValueError('File cleanup is running')
        if not isinstance(ids, list) or not ids or any(not isinstance(sid, str) for sid in ids):
            raise ValueError('Select valid cleanup items')
        with self.scan_lock:
            report, members = self._scan(days)
        by_id = {entry['id']: entry for entry in report['entries']}
        ids = list(dict.fromkeys(ids))
        if any(sid not in by_id or not by_id[sid]['allowed'] for sid in ids):
            raise ValueError('Cleanup items changed or are protected; scan again')
        entries = [by_id[sid] for sid in ids]
        manifest = {name: stat for sid in ids for name, stat in members[sid].items()}
        token = uuid.uuid4().hex
        self.plans = {token: {'home': report['home'], 'days': days, 'ids': ids,
                             'manifest': manifest, 'expires': time.time() + 300}}
        return {'token': token, 'entries': entries, 'files': len(manifest), 'bytes': sum(stat[0] for stat in manifest.values())}

    def start(self, token):
        if not self.store.operation.acquire(False): raise ValueError('Another cleanup or scan is running')
        try:
            if self.store.worker and self.store.worker.is_alive(): raise ValueError('Another cleanup or scan is running')
            plan = self.plans.pop(token, None)
            if not plan or plan['expires'] < time.time() or plan['home'] != str(self.store.home.resolve()):
                raise ValueError('Cleanup plan expired; check again')
            self.stop.clear()
            self.progress = {'running': True, 'done': 0, 'total': len(plan['manifest']), 'bytes': 0,
                             'started': time.time(), 'results': [], 'error': ''}
            threading.Thread(target=self._run, args=(plan,), daemon=True).start()
            return {'ok': True}
        except Exception:
            self.store.operation.release(); raise

    def cancel(self):
        self.stop.set()
        return {'ok': True}

    def _run(self, plan):
        results = []
        try:
            # Recheck the entire selection before deleting any file, including new references.
            with self.scan_lock:
                report, members = self._scan(plan['days'])
            allowed = {entry['id'] for entry in report['entries'] if entry['allowed']}
            fresh = {name: stat for sid in plan['ids'] for name, stat in members.get(sid, {}).items()}
            if not set(plan['ids']).issubset(allowed) or fresh != plan['manifest']:
                raise ValueError('Cleanup items changed or are protected; scan again')
            home = normal_path(plan['home'])
            for relative, stat in plan['manifest'].items():
                if self.stop.is_set(): break
                try:
                    delete_file(home, relative, stat)
                    result = {'path': relative, 'status': 'success', 'bytes': stat[0]}
                except (OSError, ValueError) as error:
                    result = {'path': relative, 'status': 'failed', 'bytes': 0, 'error': str(error)}
                results.append(result)
                self.progress = {**self.progress, 'done': len(results),
                                 'bytes': self.progress['bytes'] + result['bytes'], 'results': list(results)}
            # Remove only now-empty task/staging directories; never recursively delete a directory.
            for relative in sorted(plan['ids'], key=len, reverse=True):
                try:
                    target = safe_path(home, relative)
                    if target.is_dir():
                        directories = {parent for name in plan['manifest'] for parent in (home / name).parents
                                       if parent == target or target in parent.parents}
                        for folder in sorted(directories, key=lambda p: len(p.parts), reverse=True):
                            try: safe_path(home, folder.relative_to(home).as_posix()).rmdir()
                            except (OSError, ValueError): pass
                except (OSError, ValueError): pass
        except Exception as error:
            self.progress = {**self.progress, 'error': str(error)}
        finally:
            self.progress = {**self.progress, 'running': False, 'stopped': self.stop.is_set(), 'results': results}
            self.store.operation.release()
