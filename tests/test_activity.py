import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cleaner.activity import probe_file, thread_activity, verify_cli_protocol
from cleaner.core import detect_cli, run_cli


@unittest.skipUnless(os.name == 'nt', 'Windows writer locks')
class ProtocolVerificationTests(unittest.TestCase):
    def runner(self, behavior='compatible'):
        calls = []

        def run(args, home):
            self.assertEqual(args[:3], ['fixture.exe', 'delete', '--force'])
            self.assertTrue(home.name.startswith('cleaner-lock-check-'))
            calls.append((args, home))
            sid = args[-1]
            path = next((home / 'sessions').glob(f'*{sid}.jsonl'))
            lock = home / 'thread-writer-locks' / f'{sid}.lock'
            (lock.parent / '.coordination.lock').touch()
            if behavior == 'timeout':
                raise subprocess.TimeoutExpired(args, 12)
            busy = probe_file(lock) == 'busy'
            if behavior == 'always_refuse' or (busy and behavior != 'ignore_locks'):
                if behavior == 'mutate_locked':
                    path.write_text('changed', encoding='utf-8')
                return subprocess.CompletedProcess(args, 1, '', 'session busy')
            path.unlink()
            return subprocess.CompletedProcess(args, 0, '', '')

        return run, calls

    def test_future_version_verified_in_disposable_home(self):
        runner, calls = self.runner()
        result = verify_cli_protocol('fixture.exe', 'codex-cli future-version', runner)
        self.assertTrue(result['verified'], result)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][0][-1], calls[2][0][-1])
        self.assertNotEqual(calls[0][0][-1], calls[1][0][-1])
        self.assertEqual(len({home for _, home in calls}), 1)
        self.assertFalse(calls[0][1].exists())

    def test_incompatible_and_failed_commands_keep_deletion_disabled(self):
        for behavior in ('ignore_locks', 'always_refuse', 'mutate_locked', 'timeout'):
            with self.subTest(behavior=behavior):
                runner, calls = self.runner(behavior)
                result = verify_cli_protocol('fixture.exe', 'codex-cli future-version', runner)
                self.assertFalse(result['verified'])
                self.assertIn('验证失败', result['message'])
                self.assertFalse(calls[0][1].exists())

    def test_live_namespace_and_verification_are_both_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            sid = '00000000-0000-0000-0000-000000000001'
            self.assertEqual(thread_activity(home, sid, True)['code'], 'unknown')
            locks = home / 'thread-writer-locks'
            locks.mkdir()
            (locks / '.coordination.lock').touch()
            for unverified in (False, None, 'codex-cli future-version'):
                self.assertEqual(thread_activity(home, sid, unverified)['code'], 'unknown')
            self.assertEqual(thread_activity(home, sid, True)['code'], 'idle')
            with patch('cleaner.activity.probe_file', return_value='unknown'):
                self.assertEqual(thread_activity(home, sid, True)['code'], 'unknown')


class CliDetectionTests(unittest.TestCase):
    def test_version_is_informational_and_failed_verification_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            cli = home / 'codex.exe'
            def command(args, command_home, **kwargs):
                output = 'codex-cli future-version' if args[-1] == '--version' else '--force SESSION must be a UUID'
                return subprocess.CompletedProcess(args, 0, output, '')
            for verified in (True, False):
                with self.subTest(verified=verified), patch('cleaner.core.run_cli', side_effect=command), patch(
                        'cleaner.core.verify_cli_protocol', return_value={'verified': verified, 'message': 'verification detail'}) as verifier:
                    result = detect_cli(home, str(cli))
                    self.assertIs(result['available'], verified)
                    self.assertIs(result['lock_verified'], verified)
                    self.assertEqual(result['version'], 'codex-cli future-version')
                    self.assertEqual(result['message'], 'verification detail')
                    self.assertEqual(verifier.call_args.args[:2], (str(cli), 'codex-cli future-version'))

    def test_validation_runner_isolates_home_and_codex_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with patch.dict(os.environ, {'CODEX_HOME': 'real-home', 'CODEX_THREAD_ID': 'live',
                    'CODEX_SESSION_ID': 'live', 'CODEX_REMOTE': 'real-server'}), patch(
                    'cleaner.core.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '', '')) as command:
                run_cli(['fixture.exe', 'delete', '--force', 'fixture'], home, isolated=True)
            env = command.call_args.kwargs['env']
            self.assertEqual(env['CODEX_HOME'], str(home))
            self.assertFalse(any(key in env for key in ('CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'CODEX_REMOTE')))
            self.assertIs(command.call_args.kwargs['shell'], False)
            self.assertIs(command.call_args.kwargs['stdin'], subprocess.DEVNULL)

    def test_detect_uses_isolated_runner_for_protocol_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            def command(args, command_home, **kwargs):
                output = 'codex-cli future-version' if args[-1] == '--version' else '--force UUID'
                return subprocess.CompletedProcess(args, 0, output, '')
            def verify(cli, version, runner):
                runner([cli, 'delete', '--force', 'fixture'], home / 'isolated')
                return {'verified': True, 'message': 'passed'}
            with patch('cleaner.core.run_cli', side_effect=command) as mocked, patch(
                    'cleaner.core.verify_cli_protocol', side_effect=verify):
                detect_cli(home, str(home / 'codex.exe'))
            self.assertEqual(mocked.call_args.args[1], home / 'isolated')
            self.assertTrue(mocked.call_args.kwargs['isolated'])
