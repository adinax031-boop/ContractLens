import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from contractlens.cli import main
from tests.test_engine import spec


class CLITests(unittest.TestCase):
    def test_exit_policy_and_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b, out = (Path(temp) / n for n in ('a.json', 'b.json', 'report'))
            a.write_text(json.dumps(spec()), encoding='utf-8')
            candidate = spec(); candidate['paths'] = {}
            b.write_text(json.dumps(candidate), encoding='utf-8')
            for fmt in ('text', 'json', 'html'):
                with self.subTest(fmt=fmt):
                    self.assertEqual(main([str(a), str(b), '--format', fmt, '-o', str(out)]), 1)
                    self.assertIn('OPERATION_REMOVED' if fmt != 'html' else 'Operation Removed', out.read_text())
            self.assertEqual(main([str(a), str(b), '-o', str(out), '--fail-on', 'never']), 0)

    def test_invalid_input(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['missing.json', 'missing2.json']), 2)

    def test_warning_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / 'a.json', Path(temp) / 'b.json'
            baseline = spec(); candidate = spec(); candidate['security'] = [{'key': []}]
            a.write_text(json.dumps(baseline)); b.write_text(json.dumps(candidate))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(a), str(b)]), 0)
                self.assertEqual(main([str(a), str(b), '--fail-on', 'warning']), 1)
