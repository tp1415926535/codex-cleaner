import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows batch launcher')
class LauncherTests(unittest.TestCase):
    def run_launcher(self, *args, interpreter=True):
        env = os.environ.copy()
        system32 = str(Path(env['SYSTEMROOT']) / 'System32')
        env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + system32 if interpreter else system32
        env['PYTHONIOENCODING'] = 'utf-8'
        if not interpreter and any(shutil.which(name, path=env['PATH']) for name in ('python', 'py')):
            self.skipTest('System32 contains a Python interpreter or launcher')
        return subprocess.run(
            [env['COMSPEC'], '/d', '/c', 'start.cmd', *args], cwd=ROOT, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding='utf-8', errors='replace', timeout=15)

    def test_help_runs_without_batch_parse_errors(self):
        result = self.run_launcher('--help')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('usage: app.py', result.stdout)
        self.assertNotIn('not recognized', result.stdout)

    def test_application_failure_preserves_exit_code_and_detail(self):
        result = self.run_launcher('--fixture-invalid-option')
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('unrecognized arguments: --fixture-invalid-option', result.stdout)
        self.assertIn('启动或运行失败', result.stdout)

    def test_missing_python_explains_failure(self):
        result = self.run_launcher('--help', interpreter=False)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('未找到可用的 Python 3.10', result.stdout)
        self.assertNotIn('usage: app.py', result.stdout)


if __name__ == '__main__':
    unittest.main()
