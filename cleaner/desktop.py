"""Discover only known disposable desktop caches and diagnostic log locations."""
import ctypes
import hashlib
import os
from pathlib import Path
import re


CACHE_DIRS = ('Cache', 'Code Cache', 'GPUCache', 'DawnGraphiteCache', 'DawnWebGPUCache',
              'ShaderCache', 'GrShaderCache', 'GraphiteDawnCache', 'GPUPersistentCache',
              'Service Worker/CacheStorage', 'Service Worker/ScriptCache')
PREFIX = 'desktop-app/'


def unlinked(path):
    """Check the lexical path and all ancestors before resolving any junction."""
    try:
        return all(not part.is_symlink() and not (getattr(part.lstat(), 'st_file_attributes', 0) & 0x400)
                   for part in (path, *path.parents))
    except OSError:
        return False


def desktop_image(name, path):
    """Distinguish the Electron desktop/browser from its bundled CLI engine."""
    if path is None: return None
    name = name.casefold()
    value = str(path).replace('\\', '/').casefold()
    if '/app/resources/' in value: return False
    if '/windowsapps/openai.codex_' in value and name in ('chatgpt.exe', 'codex.exe', 'codex-browser.exe'):
        return True
    if name == 'codex.exe' and ('/openai/codex/bin/' in value or '/.codex/' in value): return False
    resources = Path(path).parent / 'resources'
    try:
        return (resources / 'app.asar').stat().st_size >= 0 and (resources / 'codex.exe').is_file()
    except FileNotFoundError: return False
    except OSError: return None


def process_images():
    """Read only candidate process image paths; inaccessible images stay unknown."""
    if os.name != 'nt': return None
    try:
        from ctypes import wintypes
        class Process(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
                        ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                        ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
                        ('exe', wintypes.WCHAR * 260)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Process)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        handle = kernel.CreateToolhelp32Snapshot(2, 0)
        if handle == ctypes.c_void_p(-1).value: return None
        try:
            process = Process(); process.size = ctypes.sizeof(process)
            if not kernel.Process32FirstW(handle, ctypes.byref(process)): return None
            images = []
            while True:
                if process.exe.casefold() in ('codex.exe', 'chatgpt.exe', 'codex-browser.exe'):
                    image = None
                    candidate = kernel.OpenProcess(0x1000, False, process.pid)
                    if candidate:
                        try:
                            buffer = ctypes.create_unicode_buffer(32768); length = wintypes.DWORD(len(buffer))
                            if kernel.QueryFullProcessImageNameW(candidate, 0, buffer, ctypes.byref(length)): image = buffer.value
                        finally: kernel.CloseHandle(candidate)
                    elif ctypes.get_last_error() == 87:
                        # The process exited after the snapshot.
                        if not kernel.Process32NextW(handle, ctypes.byref(process)):
                            return images if ctypes.get_last_error() == 18 else None
                        continue
                    images.append((process.exe, image))
                if not kernel.Process32NextW(handle, ctypes.byref(process)):
                    return images if ctypes.get_last_error() == 18 else None
        finally:
            kernel.CloseHandle(handle)
    except OSError:
        return None


def desktop_running():
    """CLI-only use does not block caches; an unknown desktop state does."""
    images = process_images()
    if images is None: return None
    states = [desktop_image(name, path) for name, path in images]
    return True if True in states else None if None in states else False


def desktop_sources(home):
    """Map stable source IDs to trusted roots and an explicit cache/log allowlist."""
    candidates, runtimes = [], []
    local, roaming = os.environ.get('LOCALAPPDATA'), os.environ.get('APPDATA')
    if roaming: candidates.append((Path(roaming) / 'Codex', 'cache', 'desktop'))
    if local:
        local = Path(local)
        runtimes.append((local / 'OpenAI/Codex', 'desktop'))
        candidates.append((local / 'Codex', 'logs', 'desktop'))
        packages = local / 'Packages'
        if unlinked(packages):
            try:
                for package in packages.glob('OpenAI.Codex_*'):
                    if not package.is_dir() or not unlinked(package): continue
                    base = package / 'LocalCache'
                    candidates.extend(((base / 'Roaming/Codex', 'cache', package.name),
                                       (base / 'Local/Codex', 'logs', package.name)))
                    runtimes.append((base / 'Local/OpenAI/Codex', package.name))
            except OSError: pass
    sources = {}
    for root, kind, installation in candidates:
        if not root.is_dir() or not unlinked(root): continue
        root = root.resolve()
        # The selected CODEX_HOME already has its own full inventory.
        if root == home or root.is_relative_to(home) or home.is_relative_to(root): continue
        targets = []
        if kind == 'logs':
            if (root / 'Logs').is_dir(): targets.append('Logs')
        else:
            bases = [root]
            browser = root / 'web/Codex'
            if browser.is_dir() and unlinked(browser):
                bases.append(browser)
                try:
                    profiles = [item for item in browser.iterdir()
                                if item.name == 'Default' or re.fullmatch(r'Profile \d+', item.name)]
                    for profile in profiles:
                        if not profile.is_dir() or not unlinked(profile): continue
                        bases.append(profile)
                        partitions = profile / 'Partitions'
                        if partitions.is_dir() and unlinked(partitions):
                            bases.extend(item for item in partitions.iterdir()
                                         if item.is_dir() and unlinked(item))
                except OSError: pass
            for base in bases:
                for name in CACHE_DIRS:
                    path = base / name
                    if path.is_dir() and unlinked(path): targets.append(path.relative_to(root).as_posix())
        if not targets: continue
        key = hashlib.sha256(os.path.normcase(str(root)).encode('utf-8')).hexdigest()[:20]
        sources[key] = {'root': root, 'kind': kind, 'installation': installation, 'targets': sorted(set(targets))}
    from .runtimes import runtime_sources
    sources.update(runtime_sources(home, runtimes))
    return sources


def resolve_desktop(home, virtual, sources=None):
    parts = virtual.split('/', 2)
    if len(parts) != 3 or parts[0] != PREFIX.rstrip('/'):
        raise ValueError('Unsafe cleanup path')
    source = (desktop_sources(home) if sources is None else sources).get(parts[1])
    relative = parts[2]
    # Never allow traversal, drive paths or arbitrary profile files through a token.
    if (not source or '\\' in relative or ':' in relative
            or any(part in ('', '.', '..') for part in relative.split('/'))
            or not any(relative == target or relative.startswith(target + '/') for target in source['targets'])
            or not unlinked(source['root'])):
        raise ValueError('Cleanup items changed or are protected; scan again')
    return source, relative
