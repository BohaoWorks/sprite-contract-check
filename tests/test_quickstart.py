"""Checks for the reproducible, two-case quickstart helper."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('quickstart', ROOT / 'examples/quickstart.py')
quickstart = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quickstart)


class QuickstartTests(unittest.TestCase):
    def test_real_cli_both_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}
            run = subprocess.run([sys.executable, str(ROOT / 'examples/quickstart.py'),
                                  '--output-dir', directory], env=env, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            for case, compatible in [('repacked', True), ('changed', False)]:
                report = Path(directory) / case
                self.assertEqual(json.loads(report.with_suffix('.json').read_text())['compatible'], compatible)
                self.assertIn('<!doctype html>', report.with_suffix('.html').read_text())

    def test_unexpected_exit_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys, 'argv', ['quickstart', '--output-dir', directory]), \
                 patch.object(quickstart.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2, '', 'bad input')):
                self.assertEqual(quickstart.main(), 2)

    def test_malformed_report_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys, 'argv', ['quickstart', '--output-dir', directory]), \
                 patch.object(quickstart.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{}', '')):
                self.assertEqual(quickstart.main(), 2)


if __name__ == '__main__':
    unittest.main()
