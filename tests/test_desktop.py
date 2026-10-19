import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cleaner.desktop import desktop_sources, resolve_desktop, desktop_running, desktop_image
from cleaner.files import FileCleanup, _DesktopCacheGuard


class DesktopCleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / '.codex'; self.home.mkdir()
        self.local = self.root / 'Local'
        self.roaming = self.root / 'Roaming'
        self.package = self.local / 'Packages/OpenAI.Codex_fixture/LocalCache'
        self.profile = self.package / 'Roaming/Codex'
        self.cache = 'web/Codex/Default/Partitions/codex-browser-app/Service Worker/CacheStorage'
        environment = patch.dict(os.environ, {'LOCALAPPDATA': str(self.local), 'APPDATA': str(self.roaming)})
        environment.start(); self.addCleanup(environment.stop)
        running = patch('cleaner.files.desktop_running', return_value=False)
        running.start(); self.addCleanup(running.stop)
        self.store = SimpleNamespace(home=self.home, current=set(), cli={}, operation=threading.Lock(), worker=None)
        self.service = FileCleanup(self.store)

    def file(self, base, relative, old=True, content='fixture'):
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        if old:
            stamp = time.time() - 100 * 86400
            os.utime(path, (stamp, stamp))
        return path

    def execute(self, plan):
        self.service.start(plan['token'])
        deadline = time.monotonic() + 10
        while self.service.progress['running'] and time.monotonic() < deadline: time.sleep(.01)
        self.assertFalse(self.service.progress['running'])
        self.assertFalse(self.store.operation.locked())
        return self.service.progress

    def test_store_and_regular_installations_scan_only_allowlisted_caches_and_logs(self):
        wanted = [self.file(self.profile, self.cache + '/origin/cache'),
                  self.file(self.profile, 'Cache/cache-entry'),
                  self.file(self.package / 'Local/Codex', 'Logs/2026/01/01/desktop.log'),
                  self.file(self.roaming / 'Codex', 'web/Codex/Profile 1/Cache/entry'),
                  self.file(self.local / 'Codex', 'Logs/plain.log')]
        preserved = [self.file(self.profile, 'web/Codex/Default/Partitions/codex-browser-app/' + name)
                     for name in ('IndexedDB/private.db', 'Local Storage/private', 'Network/Cookies',
                                  'Service Worker/Database/state', 'WebStorage/state')]
        preserved += [self.file(self.local / 'Microsoft/Edge', 'User Data/Default/Service Worker/CacheStorage/private'),
                      self.file(self.profile, 'web/Codex/artifact-sessions/user-data')]
        report = self.service.inspect()
        self.assertEqual(len(report['entries']), len(wanted))
        self.assertEqual(report['bytes'], sum(path.stat().st_size for path in wanted))
        self.assertTrue(all(Path(entry['path']).is_absolute() for entry in report['entries']))
        self.assertEqual(sum(entry['recommended'] for entry in report['entries']), 2)
        self.assertTrue(all(not entry['recommended'] for entry in report['entries'] if entry['kind'] == 'cache'))
        self.assertEqual(report['directories'], [{'name': 'desktop-app', 'bytes': report['bytes'],
                                                'files': len(wanted), 'issues': 0, 'pending': False}])
        self.assertTrue(all(path.exists() for path in preserved))

    def test_logs_group_by_date_and_respect_all_retention_periods(self):
        base = self.package / 'Local/Codex'
        self.file(base, 'Logs/2026/01/01/first.log')
        self.file(base, 'Logs/2026/01/01/second.log')
        middle = self.file(base, 'Logs/2026/10/01/middle.log')
        stamp = time.time() - 15 * 86400; os.utime(middle, (stamp, stamp))
        self.file(base, 'Logs/2026/10/19/current.log', old=False)
        for days in (7, 30, 90):
            by_path = {Path(entry['path']).relative_to(base).as_posix(): entry
                       for entry in self.service.inspect(days)['entries']}
            self.assertEqual(by_path['Logs/2026/01/01']['files'], 2)
            self.assertTrue(by_path['Logs/2026/01/01']['recommended'])
            self.assertEqual(by_path['Logs/2026/10/01']['recommended'], days == 7)
            self.assertEqual(by_path['Logs/2026/10/19']['reason'], 'recent')

    def test_running_or_unknown_app_protects_caches_but_not_old_logs(self):
        self.file(self.profile, self.cache + '/cache')
        self.file(self.package / 'Local/Codex', 'Logs/2026/01/01/desktop.log')
        for status, reason in ((True, 'desktop_running'), (None, 'desktop_unknown')):
            with patch('cleaner.files.desktop_running', return_value=status):
                report = self.service.inspect()
                cache = next(entry for entry in report['entries'] if entry['kind'] == 'cache')
                log = next(entry for entry in report['entries'] if entry['kind'] == 'logs')
                self.assertFalse(cache['allowed']); self.assertEqual(cache['reason'], reason)
                self.assertTrue(log['recommended'])
                with self.assertRaises(ValueError): self.service.plan([cache['id']])

    def test_preview_explorer_and_stream_use_actual_external_paths(self):
        path = self.file(self.package / 'Local/Codex', 'Logs/2026/01/01/desktop.log', content='diagnostic text')
        updates = list(self.service.iter_inspect())
        report = updates[-1]; entry = report['entries'][0]
        self.assertTrue(report['complete']); self.assertFalse(updates[0]['complete'])
        self.assertEqual(report['bytes'], path.stat().st_size)
        page = self.service.list_files(entry['id'], snapshot=report['snapshot'])
        name = page['items'][0]['path']
        self.assertEqual(self.service.preview(page['token'], name)['text'], 'diagnostic text')
        if os.name == 'nt':
            with patch('cleaner.files.subprocess.Popen') as launch:
                self.service.reveal(entry['id'], snapshot=report['snapshot'])
                self.assertEqual(launch.call_args.args[0], ['explorer.exe', str(path.parent)])
                self.service.reveal(token=page['token'], relative=name)
                self.assertEqual(launch.call_args.args[0], ['explorer.exe', '/select,', str(path)])

    def test_reviewed_deletion_preserves_site_data_and_cache_directories(self):
        cache = self.file(self.profile, self.cache + '/origin/cache')
        log = self.file(self.package / 'Local/Codex', 'Logs/2026/01/01/desktop.log')
        private = self.file(self.profile, 'web/Codex/Default/IndexedDB/database')
        entries = self.service.inspect()['entries']
        result = self.execute(self.service.plan([entry['id'] for entry in entries]))
        self.assertFalse(result['error'], result)
        self.assertEqual([item['status'] for item in result['results']], ['success', 'success'])
        self.assertFalse(cache.exists()); self.assertFalse(log.exists())
        self.assertTrue(cache.parent.exists()); self.assertTrue(log.parent.exists()); self.assertTrue(private.exists())

    def test_app_restart_and_changed_files_abort_reviewed_deletion(self):
        path = self.file(self.profile, self.cache + '/cache')
        entry = self.service.inspect()['entries'][0]
        plan = self.service.plan([entry['id']])
        with patch('cleaner.files.desktop_running', return_value=True): result = self.execute(plan)
        self.assertTrue(result['error']); self.assertTrue(path.exists())
        plan = self.service.plan([entry['id']])
        path.write_text('changed cache', encoding='utf-8')
        result = self.execute(plan)
        self.assertTrue(result['error']); self.assertTrue(path.exists())

    def test_app_restart_during_deletion_is_checked_again(self):
        path = self.file(self.profile, self.cache + '/cache')
        entry = self.service.inspect()['entries'][0]
        plan = self.service.plan([entry['id']])
        with patch('cleaner.files.desktop_running', side_effect=[False, True]): result = self.execute(plan)
        self.assertEqual(result['results'][0]['status'], 'skipped')
        self.assertEqual((result['success'], result['failed'], result['skipped']), (0, 0, 1))
        self.assertTrue(path.exists())

    def test_desktop_restart_skips_remaining_cache_once_and_continues_logs(self):
        cache = [self.file(self.profile, self.cache + '/' + str(index)) for index in range(20)]
        log = self.file(self.package / 'Local/Codex', 'Logs/2026/01/01/desktop.log')
        report = self.service.inspect()
        entries = sorted(report['entries'], key=lambda entry: entry['kind'] != 'cache')
        plan = self.service.plan([entry['id'] for entry in entries])
        # Initial recheck, first file, then desktop app starts.
        with patch('cleaner.files.desktop_running', side_effect=[False, False, True]) as running, \
                patch('cleaner.files.DESKTOP_CHECK_INTERVAL', 0):
            result = self.execute(plan)
        self.assertFalse(result['error'], result)
        self.assertEqual((result['success'], result['failed'], result['skipped'], result['done']), (2, 0, 19, 21))
        skipped = [item for item in result['results'] if item['status'] == 'skipped']
        self.assertEqual(len(skipped), 1); self.assertEqual(skipped[0]['files'], 19)
        self.assertEqual(skipped[0]['actual_path'], str(self.profile))
        self.assertEqual(sum(path.exists() for path in cache), 19); self.assertFalse(log.exists())
        self.assertEqual(running.call_count, 3)

    def test_cache_guard_rechecks_by_time_file_count_and_source(self):
        guard = _DesktopCacheGuard()
        with patch('cleaner.files.time.monotonic', return_value=10) as clock, \
                patch('cleaner.files.desktop_running', return_value=False) as running:
            for _ in range(32): self.assertFalse(guard.in_use('first'))
            self.assertEqual(running.call_count, 1)
            self.assertFalse(guard.in_use('first'))
            self.assertEqual(running.call_count, 2)
            clock.return_value = 10.101
            self.assertFalse(guard.in_use('first'))
            self.assertEqual(running.call_count, 3)
            self.assertFalse(guard.in_use('second'))
            self.assertEqual(running.call_count, 4)
            running.return_value = True
            clock.return_value = 10.202
            self.assertTrue(guard.in_use('second'))
            self.assertTrue(guard.in_use('third'))
            self.assertEqual(running.call_count, 5)

    def test_cache_guard_unknown_state_stays_protected(self):
        with patch('cleaner.files.desktop_running', return_value=None) as running:
            guard = _DesktopCacheGuard()
            self.assertTrue(guard.in_use('first'))
            self.assertTrue(guard.in_use('second'))
            self.assertEqual(running.call_count, 1)

    def test_desktop_restart_at_batch_boundary_preserves_remaining_cache(self):
        paths = [self.file(self.profile, self.cache + '/' + str(index)) for index in range(80)]
        entries = self.service.inspect()['entries']
        plan = self.service.plan([entry['id'] for entry in entries])
        with patch('cleaner.files.desktop_running', side_effect=[False, False, True]) as running, \
                patch('cleaner.files.DESKTOP_CHECK_INTERVAL', 60):
            result = self.execute(plan)
        self.assertFalse(result['error'], result)
        self.assertEqual((result['success'], result['failed'], result['skipped']), (32, 0, 48))
        self.assertEqual(sum(path.exists() for path in paths), 48)
        self.assertEqual(running.call_count, 3)
        self.assertEqual(len(result['results']), 33)

    def test_batched_cleanup_keeps_exact_final_results(self):
        paths = [self.file(self.profile, self.cache + '/' + str(index)) for index in range(65)]
        entries = self.service.inspect()['entries']
        result = self.execute(self.service.plan([entry['id'] for entry in entries]))
        self.assertFalse(result['error'], result)
        self.assertEqual((result['done'], result['success'], len(result['results'])), (65, 65, 65))
        self.assertTrue(all(not path.exists() for path in paths))

    def test_desktop_detection_excludes_cli_and_identifies_current_packaged_gui(self):
        package = r'C:\Program Files\WindowsApps\OpenAI.Codex_fixture\app'
        cli = self.local / 'OpenAI/Codex/bin/e78bad9887fa50cf/codex.exe'
        self.assertFalse(desktop_image('codex.exe', str(cli)))
        self.assertFalse(desktop_image('codex.exe', package + r'\resources\codex.exe'))
        self.assertTrue(desktop_image('ChatGPT.exe', package + r'\ChatGPT.exe'))
        self.assertTrue(desktop_image('Codex.exe', package + r'\Codex.exe'))
        with patch('cleaner.desktop.process_images', return_value=[('codex.exe', str(cli))]):
            self.assertIs(desktop_running(), False)
        with patch('cleaner.desktop.process_images', return_value=[('codex.exe', str(cli)), ('ChatGPT.exe', package + r'\ChatGPT.exe')]):
            self.assertIs(desktop_running(), True)
        with patch('cleaner.desktop.process_images', return_value=[('ChatGPT.exe', None)]):
            self.assertIsNone(desktop_running())

    def test_regular_desktop_detection_checks_gui_resources(self):
        executable = self.root / 'Programs/Codex/Codex.exe'
        self.file(executable.parent, 'resources/app.asar')
        self.file(executable.parent, 'resources/codex.exe')
        self.assertTrue(desktop_image('codex.exe', str(executable)))

    def test_external_capabilities_reject_traversal_and_unlisted_profile_data(self):
        self.file(self.profile, self.cache + '/cache')
        private = self.file(self.profile, 'web/Codex/Default/Network/Cookies')
        entry = self.service.inspect()['entries'][0]
        page = self.service.list_files(entry['id'])
        prefix = '/'.join(entry['id'].split('/')[:2]) + '/'
        for relative in ('../private', '/absolute', 'Cache/../../private', 'Cache/..\\private',
                         'Cache/C:/private', 'web/Codex/Default/Network/Cookies'):
            with self.subTest(relative=relative), self.assertRaises(ValueError): resolve_desktop(self.home, prefix + relative)
            with self.assertRaises(ValueError): self.service.preview(page['token'], prefix + relative)
        with self.assertRaises(ValueError): self.service.plan([prefix + 'web/Codex/Default/Network/Cookies'])
        self.assertTrue(private.exists())

    def test_changed_source_environment_expires_external_preview_and_plan(self):
        path = self.file(self.profile, self.cache + '/cache')
        entry = self.service.inspect()['entries'][0]
        page = self.service.list_files(entry['id'])
        plan = self.service.plan([entry['id']])
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.root / 'elsewhere')}):
            with self.assertRaises(ValueError): self.service.preview(page['token'], page['items'][0]['path'])
            result = self.execute(plan)
        self.assertTrue(result['error']); self.assertTrue(path.exists())

    def test_hardlinks_and_symlinked_sources_are_protected(self):
        path = self.file(self.profile, self.cache + '/cache')
        alias = self.root / 'alias'; os.link(path, alias)
        entry = self.service.inspect()['entries'][0]
        self.assertFalse(entry['allowed']); self.assertEqual(entry['reason'], 'unsafe')
        alias.unlink()
        linked_root = self.roaming / 'Codex'; linked_root.parent.mkdir(parents=True)
        try: linked_root.symlink_to(self.profile, target_is_directory=True)
        except OSError: return
        sources = desktop_sources(self.home)
        self.assertTrue(all(source['root'] != linked_root for source in sources.values()))
        self.assertEqual(len(self.service.inspect()['entries']), 1)

    @unittest.skipUnless(os.name == 'nt', 'Windows active file handles')
    def test_open_old_desktop_log_is_not_deleted(self):
        path = self.file(self.package / 'Local/Codex', 'Logs/2026/01/01/desktop.log')
        entry = self.service.inspect()['entries'][0]
        with path.open('r+b'):
            result = self.execute(self.service.plan([entry['id']]))
        self.assertEqual(result['results'][0]['status'], 'failed'); self.assertTrue(path.exists())
