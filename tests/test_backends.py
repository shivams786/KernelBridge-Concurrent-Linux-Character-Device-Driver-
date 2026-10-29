"""Mocked adapter lifecycle tests; these do not execute Linux syscalls."""

import unittest
from unittest.mock import Mock, patch

from lab.backends import LinuxDevice


class DeviceLifecycleTests(unittest.TestCase):
    def device(self):
        device = LinuxDevice.__new__(LinuxDevice)
        device.fd = 101
        device.path = "/dev/fixture"
        device.capacity = 256
        device.original_capacity = 4096
        device.abi = {"clear": 1, "set_capacity": 2}
        device.fcntl = Mock()
        return device

    def test_exit_invalidates_descriptor_and_is_idempotent(self):
        device = self.device()
        with patch("lab.backends.os.close") as close:
            device.__exit__(None, None, None)
            self.assertIsNone(device.fd)
            device.__exit__(None, None, None)
        close.assert_called_once_with(101)
        self.assertEqual(device.fcntl.ioctl.call_count, 2)

    def test_failed_close_is_not_retried(self):
        device = self.device()
        with patch("lab.backends.os.close", side_effect=OSError("close failed")) as close:
            with self.assertRaisesRegex(OSError, "close failed"):
                device.__exit__(None, None, None)
            self.assertIsNone(device.fd)
            device.__exit__(None, None, None)
        close.assert_called_once_with(101)

    def test_restore_failure_still_closes(self):
        device = self.device()
        device.fcntl.ioctl.side_effect = OSError("restore failed")
        with patch("lab.backends.os.close") as close:
            with self.assertRaisesRegex(OSError, "restore failed"):
                device.__exit__(None, None, None)
        close.assert_called_once_with(101)
        self.assertIsNone(device.fd)

    def test_setup_error_survives_close_failure(self):
        device = self.device()
        with patch("lab.backends.os.open", return_value=101), \
                patch("lab.backends.os.O_NONBLOCK", 2048, create=True), \
                patch("lab.backends.os.O_CLOEXEC", 524288, create=True), \
                patch("lab.backends.os.fstat", side_effect=ValueError("setup failed")), \
                patch("lab.backends.os.close", side_effect=OSError("close failed")):
            with self.assertRaisesRegex(ValueError, "setup failed") as caught:
                device.__enter__()
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertIsNone(device.fd)

    def test_body_error_survives_restore_failure(self):
        device = self.device()
        device.fcntl.ioctl.side_effect = OSError("restore failed")
        original = RuntimeError("workload failed")
        with patch("lab.backends.os.close") as close:
            with self.assertRaisesRegex(RuntimeError, "workload failed") as caught:
                device.__exit__(RuntimeError, original, None)
        self.assertIs(caught.exception, original)
        self.assertIsInstance(caught.exception.__cause__, OSError)
        close.assert_called_once_with(101)
        self.assertIsNone(device.fd)


if __name__ == "__main__":
    unittest.main()
