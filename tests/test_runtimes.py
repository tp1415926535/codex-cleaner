import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cleaner.files import FileCleanup
from cleaner.runtimes import EXECUTABLES, audit_runtimes, config_references, fingerprint
from cleaner.desktop import desktop_sources


class RuntimeCleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / '.codex'; self.home.mkdir()
        self.local = self.root / 'Local'
        self.runtime = self.local / 'OpenAI/Codex'
        self.install = self.root / 'Installed'
        self.resources = self.install / 'app/resources'
        environment = patch.dict(os.environ, {'LOCALAPPDATA': str(self.local), 'APPDATA': str(self.root / 'Roaming')})
        environment.start(); self.addCleanup(environment.stop)
        self.inventory = {'complete': True, 'processes': [], 'paths': [], 'references': [],
                          'packages': [{'InstallLocation': str(self.install)}]}
        inventory = patch('cleaner.runtimes.system_inventory', side_effect=lambda: self.inventory)
        inventory.start(); self.addCleanup(inventory.stop)
        configuration = patch('cleaner.runtimes.config_references', return_value=([], True))
        configuration.start(); self.addCleanup(configuration.stop)
        for name in (*EXECUTABLES[:4], 'rg.exe'): self.file(self.resources / name, 'new-' + name)
        core_key = fingerprint(self.resources, list(EXECUTABLES[:4]))
        for name in EXECUTABLES[:4]: self.file(self.runtime / 'bin' / core_key / name, 'new-' + name)
        rg_key = fingerprint(self.resources, ['rg.exe'])
        self.file(self.runtime / 'bin' / rg_key / 'rg.exe', 'new-rg.exe')
        bundle = self.resources / 'cua_node'
        for name in ('manifest.json', 'bin/node.exe', 'bin/node_repl.exe'): self.file(bundle / name, 'new-' + name)
        key = fingerprint(bundle, ['manifest.json', 'bin/node.exe', 'bin/node_repl.exe'])
        for name in ('manifest.json', 'bin/node.exe', 'bin/node_repl.exe'):
            self.file(self.runtime / 'runtimes/cua_node' / key / name, 'new-' + name)
        self.file(self.runtime / 'runtimes/cua_node' / key / 'bin/node_modules/fixture/index.js', 'module')
        self.current_codex = self.runtime / 'bin' / core_key / 'codex.exe'
        self.store = SimpleNamespace(home=self.home, current=set(), cli={'path':str(self.current_codex)},
                                     operation=threading.Lock(), worker=None)
        self.service = FileCleanup(self.store)

    def file(self, path, content='old fixture', old=True):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding='utf-8')
        if old:
            stamp = time.time() - 100 * 86400; os.utime(path, (stamp, stamp))
        return path

    def old(self, name='codex.exe'):
        return self.file(self.runtime / 'bin' / name)

    def entry(self, path):
        return next(entry for entry in self.service.inspect()['entries'] if entry['path'] == str(path))

    def execute(self, plan):
        self.service.start(plan['token'])
        deadline = time.monotonic() + 5
        while self.service.progress['running'] and time.monotonic() < deadline: time.sleep(.01)
        self.assertFalse(self.service.progress['running']); self.assertFalse(self.store.operation.locked())
        return self.service.progress

    def test_unused_legacy_and_versioned_files_are_manual_and_current_versions_protected(self):
        wanted = []
        for name in EXECUTABLES:
            if name == 'codex-code-mode-host.exe': continue
            wanted.append(self.old(name))
            wanted.append(self.file(self.local / 'Packages/OpenAI.Codex_fixture/LocalCache/Local/OpenAI/Codex/bin' / name))
        for key, name in (('0123456789abcdef', 'node.exe'), ('abcdef0123456789', 'node_repl.exe')):
            wanted.append(self.file(self.runtime / 'bin' / key / name).parent)
        report = self.service.inspect()
        manual = [entry for entry in report['entries'] if entry['allowed']]
        self.assertEqual({entry['path'] for entry in manual}, {str(path) for path in wanted})
        self.assertTrue(all(not entry['recommended'] and entry['reason'] == 'runtime_unused' for entry in manual))
        self.assertTrue(all('verified replacement' in entry['checks'] for entry in manual))
        retained = [entry for entry in report['entries'] if not entry['allowed']]
        self.assertEqual(len(retained), 3)
        self.assertTrue(all(entry['reason'] == 'runtime_current' for entry in retained))

    def test_process_arguments_startup_tasks_services_and_shortcuts_protect_old_files(self):
        path = self.old()
        for source in ('startup registry', 'scheduled task', 'service', 'shortcut', 'App Paths', 'configuration'):
            self.inventory['references'] = [{'source':source, 'value':f'"{path}" --argument'}]
            entry = self.entry(path)
            self.assertEqual(entry['reason'], 'runtime_referenced', source)
            self.assertIn(source, entry['checks'])
        self.inventory['references'] = []
        self.inventory['processes'] = [{'Name':'codex.exe', 'ExecutablePath':str(path), 'CommandLine':''}]
        self.assertEqual(self.entry(path)['reason'], 'runtime_referenced')
        self.inventory['processes'] = [{'Name':'python.exe', 'ExecutablePath':'python.exe', 'CommandLine':f'wrapper --binary "{path}"'}]
        self.assertEqual(self.entry(path)['reason'], 'runtime_referenced')

    def test_path_and_cleaner_cli_explicitly_protect_old_versions(self):
        path = self.old()
        self.inventory['paths'] = [str(path.parent)]
        self.assertEqual(self.entry(path)['reason'], 'runtime_referenced')
        self.inventory['paths'] = []
        self.store.cli['path'] = str(path)
        self.assertEqual(self.entry(path)['reason'], 'runtime_referenced')
        self.store.cli['path'] = str(self.current_codex)
        self.assertTrue(self.entry(path)['allowed'])

    def test_reference_to_flat_legacy_binary_also_protects_its_helpers(self):
        path = self.old()
        helper = self.old('codex-command-runner.exe')
        self.inventory['references'] = [{'source':'shortcut', 'value':str(path)}]
        self.assertEqual(self.entry(helper)['reason'], 'runtime_referenced')
        self.inventory['references'] = [{'source':'App Paths', 'value':str(self.root) + ';' + str(path.parent)}]
        self.assertEqual(self.entry(helper)['reason'], 'runtime_referenced')

    def test_expanded_environment_json_escaping_and_directory_configuration(self):
        path = self.old()
        values = [str(path).upper().replace('\\', '/'),
                  r'%LOCALAPPDATA%\OpenAI\Codex\bin\codex.exe',
                  r'$env:LOCALAPPDATA\OpenAI\Codex\bin\codex.exe',
                  json.dumps(str(path))]
        for value in values:
            self.inventory['references'] = [{'source':'configuration', 'value':value}]
            self.assertEqual(self.entry(path)['reason'], 'runtime_referenced', value)
        self.file(self.home / 'config.toml', 'path = ' + json.dumps(str(path.parent)))
        with patch('cleaner.runtimes.Path.home', return_value=self.root):
            references, complete = config_references(self.home)
        self.assertTrue(complete)
        self.inventory['references'] = references
        self.assertEqual(self.entry(path)['reason'], 'runtime_referenced')

    def test_incomplete_checks_and_unknown_process_path_fail_closed(self):
        path = self.old()
        self.inventory['complete'] = False
        self.assertEqual(self.entry(path)['reason'], 'runtime_unknown')
        self.inventory['complete'] = True
        self.inventory['processes'] = [{'Name':'codex.exe', 'ExecutablePath':None}]
        self.assertEqual(self.entry(path)['reason'], 'runtime_unknown')
        with self.assertRaises(ValueError): self.service.plan([self.entry(path)['id']])

    def test_missing_or_changed_successor_protects_legacy_executable(self):
        path = self.old()
        helper = self.old('codex-command-runner.exe')
        self.current_codex.write_text('corrupt successor', encoding='utf-8')
        self.assertEqual(self.entry(path)['reason'], 'runtime_unverified')
        self.assertEqual(self.entry(helper)['reason'], 'runtime_unverified')
        self.current_codex.unlink()
        self.assertEqual(self.entry(path)['reason'], 'runtime_unverified')

    def test_unknown_files_in_versioned_directory_and_private_files_are_retained(self):
        directory = self.runtime / 'bin/0123456789abcdef'
        self.file(directory / 'node.exe')
        private = self.file(directory / 'keep-my-data.txt')
        self.assertEqual(self.entry(directory)['reason'], 'runtime_unverified')
        other = self.file(self.runtime / 'bin/keep-private.txt')
        self.assertNotIn(str(other), {entry['path'] for entry in self.service.inspect()['entries']})
        self.assertTrue(private.exists())

    def test_new_reference_after_plan_stops_before_any_deletion(self):
        path = self.old()
        plan = self.service.plan([self.entry(path)['id']])
        self.inventory['references'] = [{'source':'shortcut', 'value':str(path)}]
        result = self.execute(plan)
        self.assertTrue(result['error']); self.assertEqual(result['results'], []); self.assertTrue(path.exists())

    def test_replacement_removed_after_plan_stops_deletion(self):
        path = self.old()
        plan = self.service.plan([self.entry(path)['id']])
        self.current_codex.unlink()
        result = self.execute(plan)
        self.assertTrue(result['error']); self.assertTrue(path.exists())

    def test_manual_deletion_only_removes_selected_old_program(self):
        path = self.old()
        other = self.old('node.exe')
        result = self.execute(self.service.plan([self.entry(path)['id']]))
        self.assertFalse(result['error'], result)
        self.assertEqual(result['results'][0]['status'], 'success')
        self.assertFalse(path.exists()); self.assertTrue(other.exists()); self.assertTrue(self.current_codex.exists())

    def test_recent_old_copy_and_hardlinks_are_retained(self):
        path = self.old()
        os.utime(path, None)
        self.assertEqual(self.entry(path)['reason'], 'recent')
        self.file(path)
        alias = self.root / 'alias'; os.link(path, alias)
        self.assertEqual(self.entry(path)['reason'], 'unsafe')

    def test_stream_runs_system_audit_only_once_after_inventory_is_complete(self):
        path = self.old()
        with patch('cleaner.runtimes.system_inventory', return_value=self.inventory) as audit:
            updates = list(self.service.iter_inspect())
        self.assertEqual(audit.call_count, 1)
        self.assertFalse(updates[0]['complete']); self.assertTrue(updates[-1]['complete'])
        self.assertTrue(next(entry for entry in updates[-1]['entries'] if entry['path'] == str(path))['allowed'])

    def test_cache_and_log_plans_and_execution_skip_unselected_runtime_audits(self):
        self.old()
        log = self.file(self.local / 'Codex/Logs/2026/01/01/old.log')
        cache = self.file(self.root / 'Roaming/Codex/Cache/entry')
        with patch('cleaner.files.desktop_running', return_value=False):
            report = self.service.inspect()
            for path in (log.parent, cache.parent):
                entry = next(entry for entry in report['entries'] if entry['path'] == str(path))
                with patch('cleaner.runtimes.system_inventory', side_effect=AssertionError('Unselected runtimes must not be audited')):
                    result = self.execute(self.service.plan([entry['id']]))
                self.assertFalse(result['error'], result)
                self.assertTrue(all(item['status'] == 'success' for item in result['results']))
        self.assertTrue(self.current_codex.exists())

    def test_runtime_plan_audits_only_selected_runtime_targets(self):
        selected = self.old()
        other = self.old('node.exe')
        entry = self.entry(selected)
        with patch('cleaner.files.audit_runtimes', wraps=audit_runtimes) as audit:
            self.service.plan([entry['id']])
        targets = [target for source in audit.call_args.args[1].values() for target in source['targets']]
        self.assertEqual(targets, ['bin/codex.exe'])
        self.assertTrue(other.exists())
