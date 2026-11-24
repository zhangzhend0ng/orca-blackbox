import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / "tools" / "pre_merge.py"
spec = importlib.util.spec_from_file_location("pre_merge", MODULE)
pre_merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre_merge)


class PreMergeSafetyTests(unittest.TestCase):
    def run_gate(self, root, output, scan=None):
        def fake_call(command, cwd, stdout, stderr):
            stdout.write(output.encode())
            return 1

        captured = io.StringIO()
        with patch.object(pre_merge, "CHECKS", [("synthetic", ["fake"], ())]), \
             patch.object(pre_merge.subprocess, "call", side_effect=fake_call), \
             patch.dict(os.environ, {"TEMP": str(root)}), \
             patch.object(pre_merge, "secret_count", side_effect=scan) if scan else contextlib.nullcontext():
            with contextlib.redirect_stdout(captured):
                self.assertEqual(1, pre_merge.main())
        return captured.getvalue()

    def test_secret_failure_never_prints_log_tail_and_deletes_log(self):
        with tempfile.TemporaryDirectory() as root:
            sentinel = "password=AbCdEf0123456789"
            result = self.run_gate(Path(root), "ordinary line\n" + sentinel + "\n")
            self.assertNotIn(sentinel, result)
            self.assertEqual([], list(Path(root).glob("orca-bb-pre_merge-*/1-synthetic.log")))

    def test_scan_failure_is_suppressed_and_log_deleted(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_gate(Path(root), "tail contains private output\n", lambda _path: -1)
            self.assertNotIn("private output", result)
            self.assertIn("scan unsafe", result)
            self.assertEqual([], list(Path(root).glob("orca-bb-pre_merge-*/1-synthetic.log")))

    def test_temp_directories_are_unique(self):
        with tempfile.TemporaryDirectory() as root:
            first = self.run_gate(Path(root), "first private line\n", lambda _path: 0)
            second = self.run_gate(Path(root), "second private line\n", lambda _path: 0)
            dirs = list(Path(root).glob("orca-bb-pre_merge-*"))
            self.assertEqual(2, len(dirs))
            self.assertNotEqual(dirs[0], dirs[1])
            self.assertTrue((dirs[0] / "1-synthetic.log").exists())
            self.assertTrue((dirs[1] / "1-synthetic.log").exists())
            self.assertNotIn("private line", first + second)

    def test_delete_failure_is_reported_without_log_tail(self):
        with tempfile.TemporaryDirectory() as root:
            sentinel = "private delete failure output"
            with patch.object(pre_merge.os, "remove", side_effect=OSError("locked")):
                result = self.run_gate(Path(root), sentinel + "\n", lambda _path: 1)
            self.assertNotIn(sentinel, result)
            self.assertIn("log removal failed", result)
            self.assertNotIn("log removed", result)


if __name__ == "__main__":
    unittest.main()
