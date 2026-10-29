"""Portable checks of validation evidence, timeout handling, and snapshots."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from lab.validate_linux import main, new_kernel_messages, run_step, snapshot


class LinuxValidationTests(unittest.TestCase):
    def test_command_exit_status_and_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_step("failure", [sys.executable, "-c", "print('diagnostic'); raise SystemExit(7)"], root, root)
            self.assertEqual(result["exit_code"], 7)
            self.assertEqual(result["status"], "failed")
            self.assertIn("diagnostic", (root / "failure.log").read_text())
            result = run_step("success", [sys.executable, "-c", "print('ok')"], root, root)
            self.assertEqual(result["status"], "passed")

    def test_timeout_does_not_become_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_step("timeout", [sys.executable, "-c", "import time; time.sleep(10)"], root, root, timeout=0.1)
            self.assertEqual(result["status"], "timeout")
            self.assertIsNotNone(result["exit_code"])

    def test_missing_executable_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_step("missing", [str(root / "not-a-program")], root, root)
            self.assertEqual(result["status"], "failed")
            self.assertIn("error", result)

    def test_kernel_log_rotation_is_inconclusive(self):
        self.assertEqual(new_kernel_messages("boot\nold\n", "old\nnew\n")["status"], "inconclusive")
        self.assertEqual(new_kernel_messages("boot\n", "boot\nloaded\n")["status"], "passed")
        result = new_kernel_messages("boot\n", "boot\nBUG: bad access\n")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["findings"], ["BUG: bad access"])

    def test_snapshot_records_shell_normalization_and_dirty_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "source with spaces", root / "build"
            source.mkdir()
            (source / "test.sh").write_bytes(b"#!/bin/bash\r\ntrue\r\n")
            (source / "source.c").write_bytes(b"/* working tree change */\r\n")
            records = snapshot(source, target, ["test.sh", "source.c", "deleted.c"])
            self.assertTrue(records["test.sh"]["normalized_shell_crlf"])
            self.assertNotEqual(records["test.sh"]["working_sha256"], records["test.sh"]["build_sha256"])
            self.assertEqual((target / "test.sh").read_bytes(), b"#!/bin/bash\ntrue\n")
            self.assertEqual((target / "source.c").read_bytes(), (source / "source.c").read_bytes())
            self.assertNotIn("deleted.c", records)

    def test_snapshot_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                snapshot(root, root / "build", ["../outside"])

    def test_non_linux_is_blocked_before_commands(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "blocked"
            with patch("lab.validate_linux.platform.system", return_value="Windows"), \
                    patch("lab.validate_linux.run_step") as run:
                self.assertEqual(main(["--output", str(output)]), 2)
                run.assert_not_called()
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "blocked")
            self.assertFalse(manifest["runtime_validated"])
            self.assertEqual(manifest["steps"], [])


if __name__ == "__main__":
    unittest.main()
