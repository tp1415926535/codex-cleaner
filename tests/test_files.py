import json
import base64
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
import urllib.request
import urllib.error
from urllib.parse import urlencode

from cleaner.files import FileCleanup, delete_file, identity
from cleaner.core import Store
from app import make_server


class FileCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.store = SimpleNamespace(home=self.home, current=set(), cli={'version': 'codex-cli current'},
                                     operation=threading.Lock(), worker=None)
        self.service = FileCleanup(self.store)

    def tearDown(self):
        self.temporary.cleanup()

    def file(self, relative, old=True, content='fixture'):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        if old:
            stamp = time.time() - 100 * 86400
            os.utime(path, (stamp, stamp))
        return path

    def run_plan(self, ids):
        plan = self.service.plan(ids)
        self.service.start(plan['token'])
        deadline = time.monotonic() + 5
        while self.service.progress['running'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.service.progress['running'])
        self.assertFalse(self.store.operation.locked())
        return self.service.progress

    def test_inventory_and_recommendation_preserve_user_data_and_current_files(self):
        self.file('.sandbox/sandbox.2026-01-01.log')
        self.file('.sandbox/sandbox.2026-10-12.log', old=False)
        self.file('.sandbox/deny_read_acl_state.json')
        self.file('cache/codex_apps_tools/old.json')
        self.file('cache/bundled_plugin_exclusions/prefs.json')
        self.file('..codex-global-state.json.tmp-123-uuid')
        self.file('config.toml.bak-old')
        self.file('skills/custom/SKILL.md')
        artifact = 'generated_images/' + str(uuid.uuid4())
        self.file(artifact + '/image.png')
        report = self.service.inspect()
        entries = {entry['id']: entry for entry in report['entries']}
        recommended = {entry['id'] for entry in report['entries'] if entry['recommended']}
        self.assertEqual(recommended, {'.sandbox/sandbox.2026-01-01.log', 'cache/codex_apps_tools/old.json', '..codex-global-state.json.tmp-123-uuid'})
        self.assertEqual(entries['.sandbox/sandbox.2026-10-12.log']['reason'], 'recent')
        self.assertTrue(entries[artifact]['allowed'])
        self.assertFalse(entries[artifact]['recommended'])
        self.assertTrue(entries['config.toml.bak-old']['allowed'])
        self.assertEqual({folder['name'] for folder in report['directories']}, {'.sandbox', 'cache', 'skills', 'generated_images'})

    def test_configuration_reference_blocks_tmp_marketplace_and_invalid_config_blocks_temporary(self):
        target = '.tmp/bundled-marketplaces/openai-bundled'
        self.file(target + '/plugin/SKILL.md')
        self.file('.tmp/legacy-primary-runtime-skills/old.md')
        source = str(self.home / target)
        self.file('config.toml', content="[marketplaces.bundled]\nsource = '" + source + "'\n")
        entries = {entry['id']: entry for entry in self.service.inspect()['entries']}
        self.assertEqual(entries[target]['reason'], 'referenced')
        self.assertTrue(entries['.tmp/legacy-primary-runtime-skills']['recommended'])
        self.file('.codex-global-state.json', content=json.dumps({'data_directory': str(self.home)}))
        self.file('.sandbox/sandbox.2026-01-01.log')
        entries = {entry['id']: entry for entry in self.service.inspect()['entries']}
        self.assertTrue(entries['.sandbox/sandbox.2026-01-01.log']['recommended'])
        if os.name == 'nt':
            self.file('config.toml', content="source = '\\\\?\\" + source + "'\n")
            entries = {entry['id']: entry for entry in self.service.inspect()['entries']}
            self.assertEqual(entries[target]['reason'], 'referenced')
        self.file('config.toml', content='broken = [')
        entries = self.service.inspect()['entries']
        self.assertTrue(all(not entry['allowed'] for entry in entries if entry['category'] == '.tmp'))

    def test_current_and_open_artifact_directories_are_protected(self):
        active, opened, idle = [str(uuid.uuid4()) for _ in range(3)]
        for sid in (active, opened, idle): self.file('visualizations/2026/10/12/' + sid + '/index.html')
        self.store.current.add(active)
        self.file('.codex-global-state.json', content=json.dumps({'electron-persisted-atom-state': {
            'thread-tab-routes-v1:opened': {'routes':[{'params':{'path':str(self.home / 'visualizations/2026/10/12' / opened / 'index.html')}}]},
            'heartbeat-thread-permissions-by-id': {'old':str(self.home / 'visualizations/2026/10/12' / idle)}}}))
        entries = {entry['id'].split('/')[-1]: entry for entry in self.service.inspect()['entries']}
        self.assertEqual(entries[active]['reason'], 'active')
        self.assertEqual(entries[opened]['reason'], 'referenced')
        self.assertTrue(entries[idle]['allowed'])

    def test_current_and_recent_runners_are_retained(self):
        for index, name in enumerate(('old', 'recent', 'current')):
            path = self.file(f'.sandbox-bin/codex-command-runner-{name}.exe')
            stamp = time.time() - (100-index) * 86400
            os.utime(path, (stamp, stamp))
        self.file('.sandbox-bin/codex.exe')
        entries = {entry['id']: entry for entry in self.service.inspect()['entries']}
        self.assertTrue(entries['.sandbox-bin/codex-command-runner-old.exe']['recommended'])
        self.assertFalse(entries['.sandbox-bin/codex-command-runner-current.exe']['allowed'])
        self.assertFalse(entries['.sandbox-bin/codex-command-runner-recent.exe']['allowed'])
        self.assertNotIn('.sandbox-bin/codex.exe', entries)

    def test_staging_coordination_lock_protects_temporary_directories(self):
        self.file('.tmp/plugins.sync.lock')
        self.file('.tmp/legacy-primary-runtime-skills/old.md')
        with patch('cleaner.files.probe_file', return_value='busy'):
            entry = self.service.inspect()['entries'][0]
        self.assertEqual(entry['reason'], 'active')
        self.assertFalse(entry['recommended'])

    def test_directory_file_list_is_complete_searchable_and_paginated(self):
        directory = '.tmp/legacy-primary-runtime-skills'
        for index in range(205): self.file(f'{directory}/nested/file-{index:03d}.md')
        first = self.service.list_files(directory)
        second = self.service.list_files(directory, offset=first['next'])
        last = self.service.list_files(directory, offset=second['next'])
        paths = [item['path'] for page in (first,second,last) for item in page['items']]
        self.assertEqual(first['total'], 205)
        self.assertEqual((len(first['items']),len(second['items']),len(last['items'])), (100,100,5))
        self.assertEqual(len(set(paths)), 205)
        self.assertIsNone(last['next'])
        self.assertEqual(self.service.list_files(directory, offset=5000)['offset'], 200)
        found = self.service.list_files(directory, query='FILE-204')
        self.assertEqual(found['matched'], 1)
        self.assertTrue(found['items'][0]['path'].endswith('file-204.md'))
        self.assertEqual(self.service.list_files(directory, query='absent')['items'], [])
        for sid in ('../outside', 'auth.json', '.tmp'):
            with self.subTest(sid=sid), self.assertRaises(ValueError): self.service.list_files(sid)
        with self.assertRaises(ValueError): self.service.list_files(directory, offset=-1)

    def test_creation_time_identity_is_consistent_between_path_and_handle(self):
        path = SimpleNamespace(st_size=7, st_mtime_ns=1, st_ctime_ns=2, st_birthtime_ns=2,
                               st_dev=3, st_ino=4, st_nlink=1)
        handle = SimpleNamespace(**vars(path))
        handle.st_ctime_ns = 999
        self.assertEqual(identity(path), identity(handle))
        handle.st_ino = 5
        self.assertNotEqual(identity(path), identity(handle))

    def test_inspection_snapshot_browses_pages_and_search_without_rescanning(self):
        directory = '.tmp/legacy-primary-runtime-skills'
        for index in range(105): self.file(f'{directory}/file-{index:03d}.md')
        report = self.service.inspect()
        with patch.object(self.service, '_scan', side_effect=AssertionError('Browsing must not rescan')):
            first = self.service.list_files(directory, snapshot=report['snapshot'])
            second = self.service.list_files(directory, offset=first['next'], snapshot=report['snapshot'])
            found = self.service.list_files(directory, query='104', snapshot=report['snapshot'])
            self.assertEqual(len(first['items']), 100)
            self.assertEqual(len(second['items']), 5)
            self.assertEqual(found['matched'], 1)
            with self.assertRaises(ValueError): self.service.list_files(directory, days=30, snapshot=report['snapshot'])
            with self.assertRaises(ValueError): self.service.list_files('auth.json', snapshot=report['snapshot'])
            with self.assertRaises(ValueError): self.service.list_files(directory, snapshot='unknown')
        self.store.home = self.home / directory
        with self.assertRaises(ValueError): self.service.list_files(directory, snapshot=report['snapshot'])

    def test_streaming_scan_lists_directories_and_partial_items_before_completion(self):
        log = self.file('.sandbox/sandbox.2026-01-01.log')
        artifact = 'visualizations/' + str(uuid.uuid4())
        self.file(artifact + '/notes.md')
        iterator = self.service.iter_inspect()
        initial = next(iterator)
        self.assertFalse(initial['complete'])
        self.assertEqual(initial['entries'], [])
        self.assertEqual({folder['name'] for folder in initial['directories']}, {'.sandbox', 'visualizations'})
        partial = next(iterator)
        self.assertFalse(partial['complete'])
        self.assertEqual(partial['entries'][0]['id'], log.relative_to(self.home).as_posix())
        self.assertFalse(partial['entries'][0]['allowed'])
        self.assertEqual(partial['entries'][0]['reason'], 'scanning')
        with patch.object(self.service, '_scan', side_effect=AssertionError('Partial preview must use its snapshot')):
            files = self.service.list_files(partial['entries'][0]['id'], snapshot=partial['snapshot'])
            self.assertEqual(self.service.preview(files['token'], files['items'][0]['path'])['text'], 'fixture')
        final = list(iterator)[-1]
        self.assertTrue(final['complete'])
        self.assertEqual(final['snapshot'], partial['snapshot'])
        self.assertEqual(len(final['entries']), 2)
        self.assertTrue(next(entry for entry in final['entries'] if entry['id'].startswith('.sandbox'))['recommended'])
        self.assertTrue(all(not folder['pending'] for folder in final['directories']))
        self.assertFalse(self.service.scan_lock.locked())

    def test_closing_stream_releases_scan_lock_and_inventory_keeps_full_identity(self):
        path = self.file('.sandbox/sandbox.2026-01-01.log')
        iterator = self.service.iter_inspect()
        next(iterator);iterator.close()
        self.assertFalse(self.service.scan_lock.locked())
        manifest, _, _ = self.service._inventory(self.home)
        self.assertEqual(manifest[path.relative_to(self.home).as_posix()], identity(path.stat()))

    def test_preview_and_cached_browsing_do_not_wait_for_inspection_lock(self):
        directory = '.tmp/legacy-primary-runtime-skills'
        self.file(directory + '/readme.md', content='already indexed')
        report = self.service.inspect()
        page = self.service.list_files(directory, snapshot=report['snapshot'])
        results, errors = [], []
        def browse():
            try:
                results.append(self.service.list_files(directory, snapshot=report['snapshot']))
                results.append(self.service.preview(page['token'], directory + '/readme.md'))
            except Exception as error: errors.append(error)
        self.service.scan_lock.acquire()
        worker = threading.Thread(target=browse, daemon=True)
        try:
            worker.start();worker.join(2)
            blocked = worker.is_alive()
        finally:
            self.service.scan_lock.release();worker.join(2)
        self.assertFalse(blocked, 'Cached lists and previews must not wait for a full scan')
        self.assertEqual(errors, [])
        self.assertEqual(results[1]['text'], 'already indexed')

    def test_preview_reads_text_without_running_markup_and_bounds_large_files(self):
        directory = '.tmp/legacy-primary-runtime-skills'
        markup = '<script>window.executed=true</script>\n中文内容'
        path = self.file(directory + '/index.html', content=markup)
        page = self.service.list_files(directory)
        self.assertEqual(self.service.preview(page['token'], path.relative_to(self.home).as_posix())['text'], markup)
        self.file(directory + '/large.md', content='中文' * 100000)
        page = self.service.list_files(directory)
        result = self.service.preview(page['token'], directory + '/large.md')
        self.assertTrue(result['truncated'])
        self.assertLessEqual(len(result['text'].encode('utf-8')), 256 * 1024)
        self.assertNotIn('\ufffd', result['text'])
        path = self.file(directory + '/utf16.txt')
        path.write_bytes('中文 UTF16'.encode('utf-16'))
        page = self.service.list_files(directory)
        self.assertEqual(self.service.preview(page['token'], directory + '/utf16.txt')['text'], '中文 UTF16')

    def test_preview_capability_rejects_other_files_expiry_home_and_file_changes(self):
        directory = '.tmp/legacy-primary-runtime-skills'
        path = self.file(directory + '/readme.md')
        self.file('auth.json', content='private')
        page = self.service.list_files(directory)
        for name in ('auth.json', '../auth.json', directory + '/missing.md'):
            with self.subTest(name=name), self.assertRaises(ValueError): self.service.preview(page['token'], name)
        with self.assertRaises(ValueError): self.service.preview('invalid', directory + '/readme.md')
        path.write_text('changed file', encoding='utf-8')
        with self.assertRaises(ValueError): self.service.preview(page['token'], directory + '/readme.md')
        page = self.service.list_files(directory)
        self.service.previews[page['token']]['expires'] = 0
        with self.assertRaises(ValueError): self.service.preview(page['token'], directory + '/readme.md')
        page = self.service.list_files(directory)
        self.store.home = self.home / directory
        with self.assertRaises(ValueError): self.service.preview(page['token'], directory + '/readme.md')

    def test_preview_rejects_hardlinks_and_replaced_symlinks(self):
        directory = '.tmp/legacy-primary-runtime-skills'
        path = self.file(directory + '/readme.md')
        page = self.service.list_files(directory)
        alias = self.home / 'alias'
        os.link(path, alias)
        with self.assertRaises(ValueError): self.service.preview(page['token'], directory + '/readme.md')
        page = self.service.list_files(directory)
        with self.assertRaises(ValueError): self.service.preview(page['token'], directory + '/readme.md')
        alias.unlink()
        page = self.service.list_files(directory)
        path.unlink()
        target = self.file('auth.json', content='private')
        try: path.symlink_to(target)
        except OSError: return
        with self.assertRaises(ValueError): self.service.preview(page['token'], directory + '/readme.md')

    def test_images_are_bounded_and_binary_files_are_not_executed(self):
        directory = '.tmp/legacy-primary-runtime-skills'
        image = self.file(directory + '/image.png')
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jx4QAAAAASUVORK5CYII=')
        image.write_bytes(png)
        self.file(directory + '/not-image.png', content='<script>bad</script>')
        self.file(directory + '/script.exe', content='do not execute')
        binary = self.file(directory + '/unknown.dat');binary.write_bytes(b'\x00\xff\x01')
        large = self.file(directory + '/large.png')
        with large.open('wb') as stream: stream.truncate(16 * 1024 * 1024 + 1)
        page = self.service.list_files(directory)
        self.assertEqual(self.service.image(page['token'], directory + '/image.png'), (png, 'image/png'))
        for name in ('not-image.png', 'large.png', 'script.exe'):
            with self.subTest(name=name), self.assertRaises(ValueError): self.service.image(page['token'], directory + '/' + name)
        for name in ('script.exe', 'unknown.dat', 'large.png'):
            self.assertEqual(self.service.preview(page['token'], directory + '/' + name)['kind'], 'unsupported')

    @unittest.skipUnless(os.name == 'nt', 'Windows Explorer')
    def test_open_folder_launches_only_explorer_and_validates_paths(self):
        directory = '.tmp/legacy-primary-runtime-skills'
        path = self.file(directory + '/note.md')
        page = self.service.list_files(directory)
        with patch('cleaner.files.subprocess.Popen') as launch:
            report = self.service.inspect()
            with patch.object(self.service, '_scan', side_effect=AssertionError('Opening a folder must not rescan')):
                self.service.reveal(directory, snapshot=report['snapshot'])
            self.assertEqual(launch.call_args.args[0], ['explorer.exe', str(self.home / directory)])
            self.service.reveal(token=page['token'], relative=directory + '/note.md')
            self.assertEqual(launch.call_args.args[0], ['explorer.exe', '/select,', str(path)])
            with self.assertRaises(ValueError): self.service.reveal('auth.json')
            with self.assertRaises(ValueError): self.service.reveal(token=page['token'], relative='../outside')
            self.assertEqual(launch.call_count, 2)

    @unittest.skipUnless(os.name == 'nt', 'Windows extended paths')
    def test_extended_home_uses_the_same_checked_file_identity(self):
        path = self.file('.sandbox/sandbox.2026-01-01.log')
        self.store.home = Path('\\\\?\\' + str(self.home))
        result = self.run_plan([path.relative_to(self.home).as_posix()])
        self.assertEqual(result['results'][0]['status'], 'success', result)
        self.assertFalse(path.exists())

    def test_deletion_removes_only_reviewed_files_and_preserves_lock_files(self):
        old = self.file('.tmp/legacy-primary-runtime-skills/nested/old.md')
        lock = self.file('.tmp/legacy-primary-runtime-skills/runtime.lock')
        keep = self.file('auth.json')
        result = self.run_plan(['.tmp/legacy-primary-runtime-skills'])
        self.assertEqual(result['done'], 1)
        self.assertEqual(result['results'][0]['status'], 'success', result)
        self.assertFalse(old.exists())
        self.assertTrue(lock.exists())
        self.assertTrue(keep.exists())

    def test_file_change_after_confirmation_blocks_entire_batch(self):
        a = self.file('.sandbox/sandbox.2026-01-01.log')
        b = self.file('.sandbox/sandbox.2026-01-02.log')
        plan = self.service.plan([a.relative_to(self.home).as_posix(), b.relative_to(self.home).as_posix()])
        a.write_text('changed', encoding='utf-8')
        self.store.operation.acquire()
        self.service._run(self.service.plans.pop(plan['token']))
        self.assertIn('changed', self.service.progress['error'])
        self.assertTrue(a.exists()); self.assertTrue(b.exists())
        self.assertEqual(self.service.progress['done'], 0)

    def test_new_reference_blocks_plan_and_unknown_paths_are_rejected(self):
        target = '.tmp/legacy-primary-runtime-skills'
        self.file(target + '/old.md')
        plan = self.service.plan([target])
        self.file('config.toml', content="source = '" + str(self.home / target) + "'")
        self.store.operation.acquire()
        self.service._run(self.service.plans.pop(plan['token']))
        self.assertTrue(self.service.progress['error'])
        self.assertTrue((self.home / target / 'old.md').exists())
        for ids in (['../outside'], ['auth.json'], [], ['.tmp'], 'bad'):
            with self.subTest(ids=ids), self.assertRaises(ValueError): self.service.plan(ids)

    def test_hardlinks_and_symlinks_cannot_be_recommended_or_deleted(self):
        path = self.file('.sandbox/sandbox.2026-01-01.log')
        alias = self.home / 'alias.log'
        os.link(path, alias)
        entry = self.service.inspect()['entries'][0]
        self.assertFalse(entry['allowed'])
        with self.assertRaises(ValueError): delete_file(self.home, entry['id'], identity(path.stat()))
        alias.unlink()
        try: (self.home / '.tmp').symlink_to(self.home / '.sandbox', target_is_directory=True)
        except OSError: return
        with self.assertRaises(ValueError): delete_file(self.home, '.tmp/sandbox.2026-01-01.log', identity(path.stat()))
        self.assertTrue(path.exists())

    def test_stop_and_operation_lock(self):
        a = self.file('.sandbox/sandbox.2026-01-01.log')
        b = self.file('.sandbox/sandbox.2026-01-02.log')
        ids = [path.relative_to(self.home).as_posix() for path in (a,b)]
        plan = self.service.plan(ids)
        self.store.operation.acquire()
        with self.assertRaises(ValueError): self.service.start(plan['token'])
        self.store.operation.release()
        def stop_after_one(home, relative, stat):
            try: delete_file(home, relative, stat)
            finally: self.service.stop.set()
        with patch('cleaner.files.delete_file', side_effect=stop_after_one): result = self.run_plan(ids)
        self.assertEqual(result['done'], 1)
        self.assertTrue(result['stopped'])
        successes = sum(item['status'] == 'success' for item in result['results'])
        self.assertEqual(sum(path.exists() for path in (a,b)), 2-successes)

    @unittest.skipUnless(os.name == 'nt', 'Windows file handles')
    def test_active_writer_is_not_deleted(self):
        path = self.file('.sandbox/sandbox.2026-01-01.log')
        with path.open('r+b'):
            result = self.run_plan([path.relative_to(self.home).as_posix()])
        self.assertEqual(result['results'][0]['status'], 'failed')
        self.assertTrue(path.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows read-only files')
    def test_readonly_git_pack_objects_are_deleted_through_checked_handles(self):
        paths = [self.file('.tmp/plugins/.git/objects/pack/pack-fixture.' + suffix) for suffix in ('idx', 'pack', 'rev')]
        for path in paths: path.chmod(0o444)
        try:
            self.assertTrue(all(path.stat().st_file_attributes & 1 for path in paths))
            result = self.run_plan(['.tmp/plugins'])
            self.assertEqual([item['status'] for item in result['results']], ['success'] * 3)
            self.assertTrue(all(not path.exists() for path in paths))
        finally:
            for path in paths:
                if path.exists(): path.chmod(0o666)

    @unittest.skipUnless(os.name == 'nt', 'Windows read-only files')
    def test_readonly_file_with_writer_remains_unchanged(self):
        path = self.file('.sandbox/sandbox.2026-01-01.log')
        writer = path.open('r+b')
        path.chmod(0o444)
        try:
            result = self.run_plan([path.relative_to(self.home).as_posix()])
            self.assertEqual(result['results'][0]['status'], 'failed')
            self.assertTrue(path.exists())
            self.assertTrue(path.stat().st_file_attributes & 1)
        finally:
            writer.close();path.chmod(0o666)

    @unittest.skipUnless(os.name == 'nt', 'Windows read-only files')
    def test_changed_readonly_file_is_not_deleted_or_made_writable(self):
        path = self.file('.sandbox/sandbox.2026-01-01.log')
        expected = identity(path.stat())
        path.write_text('changed after inspection', encoding='utf-8')
        path.chmod(0o444)
        try:
            with self.assertRaises(ValueError): delete_file(self.home, path.relative_to(self.home).as_posix(), expected)
            self.assertTrue(path.exists())
            self.assertTrue(path.stat().st_file_attributes & 1)
        finally: path.chmod(0o666)

    def test_http_cleanup_requires_csrf_and_explicit_confirmation(self):
        path = self.file('.sandbox/sandbox.2026-01-01.log')
        store = Store(self.home)
        server = make_server(store, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def post(endpoint, data, headers):
            request = urllib.request.Request(base + endpoint, data=json.dumps(data).encode(),
                      headers={'Content-Type':'application/json', **headers})
            return json.load(urllib.request.urlopen(request))
        try:
            csrf = json.load(urllib.request.urlopen(base + '/api/state'))['csrf']
            with urllib.request.urlopen(base + '/api/files-inspect?stream=1') as response:
                self.assertIn('application/x-ndjson', response.headers['Content-Type'])
                updates = [json.loads(line) for line in response if line.strip()]
            self.assertFalse(updates[0]['complete'])
            self.assertTrue(updates[-1]['complete'])
            report = json.load(urllib.request.urlopen(base + '/api/files-inspect'))
            with patch.object(store.files, '_scan', side_effect=AssertionError('HTTP browsing must reuse the inspection')):
                cached = json.load(urllib.request.urlopen(base + '/api/files-list?' + urlencode({
                    'id':path.relative_to(self.home).as_posix(), 'snapshot':report['snapshot']})))
                self.assertEqual(cached['total'], 1)
            files = json.load(urllib.request.urlopen(base + '/api/files-list?id=.sandbox%2Fsandbox.2026-01-01.log'))
            self.assertEqual(files['total'], 1)
            self.assertEqual(files['items'][0]['path'], path.relative_to(self.home).as_posix())
            headers = {'Origin':base, 'X-CSRF-Token':csrf}
            query = urlencode({'token': files['token'], 'path': files['items'][0]['path']})
            preview = json.load(urllib.request.urlopen(base + '/api/files-preview?' + query))
            self.assertEqual(preview['text'], 'fixture')
            directory = '.tmp/legacy-primary-runtime-skills'
            image = self.file(directory + '/image.png')
            png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jx4QAAAAASUVORK5CYII=')
            image.write_bytes(png)
            image_list = json.load(urllib.request.urlopen(base + '/api/files-list?' + urlencode({'id':directory})))
            image_query = urlencode({'token':image_list['token'], 'path':directory + '/image.png'})
            with urllib.request.urlopen(base + '/api/files-image?' + image_query) as response:
                self.assertEqual(response.headers['Content-Type'], 'image/png')
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(response.read(), png)
            with self.assertRaises(urllib.error.HTTPError) as blocked:
                urllib.request.urlopen(base + '/api/files-image?' + urlencode({'token':image_list['token'], 'path':'auth.json'}))
            self.assertEqual(blocked.exception.code, 400)
            with patch.object(store.files, 'reveal', return_value={'ok': True}) as reveal:
                with self.assertRaises(urllib.error.HTTPError) as blocked:
                    post('/api/files-reveal', {'id': files['id']}, {})
                self.assertEqual(blocked.exception.code, 403)
                reveal.assert_not_called()
                self.assertTrue(post('/api/files-reveal', {'id': files['id']}, headers)['ok'])
                reveal.assert_called_once()
            request = urllib.request.Request(base + '/api/files-preview?' + query, headers={'Origin':'https://external.example'})
            with self.assertRaises(urllib.error.HTTPError) as blocked: urllib.request.urlopen(request)
            self.assertEqual(blocked.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError) as blocked:
                post('/api/files-plan', {'ids':[path.relative_to(self.home).as_posix()]}, {})
            self.assertEqual(blocked.exception.code, 403)
            plan = post('/api/files-plan', {'ids':[path.relative_to(self.home).as_posix()]}, headers)
            with self.assertRaises(urllib.error.HTTPError) as unconfirmed:
                post('/api/files-start', {'token':plan['token']}, headers)
            self.assertEqual(unconfirmed.exception.code, 400)
            self.assertTrue(path.exists())
            post('/api/files-start', {'token':plan['token'], 'confirmed':True}, headers)
            deadline = time.monotonic()+5
            while store.files.progress['running'] and time.monotonic()<deadline: time.sleep(.01)
            self.assertFalse(path.exists())
        finally:
            server.shutdown(); server.server_close(); worker.join()
