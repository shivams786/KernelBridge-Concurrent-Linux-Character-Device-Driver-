"""Independent simulator and Linux syscall adapter for the contract runner."""

from collections import deque
import errno
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import threading

from .contract import failure, success


class SimulatedDevice:
    """Test fixture, never evidence that the kernel implementation passes."""

    def __init__(self, capacity, fault="none"):
        self.capacity = capacity
        self.queue = deque()
        self.fault = fault
        self.lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def apply(self, op):
        with self.lock:
            return self._apply_locked(op)

    def _apply_locked(self, op):
        kind = op["op"]
        if kind == "write":
            payload = bytes.fromhex(op["data"])
            if payload and len(self.queue) == self.capacity:
                return failure(errno.EAGAIN)
            transferred = 0
            for value in payload:
                if len(self.queue) == self.capacity:
                    break
                self.queue.append(value)
                transferred += 1
            return success(transferred)
        if kind == "read":
            if op["count"] and not self.queue:
                if self.fault == "false-eof":
                    return success(0, b"")
                return failure(errno.EAGAIN)
            values = []
            for _ in range(op["count"]):
                if not self.queue:
                    break
                values.append(self.queue.popleft())
            if self.fault == "reverse-read":
                values.reverse()
            return success(len(values), bytes(values))
        if kind == "resize":
            requested = op["capacity"]
            if requested < 256 or requested > 65536:
                return failure(errno.EINVAL)
            if requested < len(self.queue):
                return failure(errno.EMSGSIZE)
            self.capacity = requested
            if self.fault == "resize-loss":
                self.queue.clear()
            return success()
        if kind == "clear":
            self.queue.clear()
            return success()
        if kind == "capacity":
            return success(self.capacity)
        raise ValueError("unknown operation")


class LinuxDevice:
    def __init__(self, capacity, path, abi_program):
        if sys.platform != "linux":
            raise RuntimeError("real-device backend requires Linux")
        import fcntl
        self.fcntl = fcntl
        self.path = path
        self.capacity = capacity
        self.fd = None
        self.abi = json.loads(subprocess.check_output(
            [str(Path(abi_program).resolve())], text=True, timeout=5))
        if (self.abi["abi_version"], self.abi["min_capacity"], self.abi["max_capacity"]) != (1, 256, 65536):
            raise ValueError("unsupported device ABI")

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            if not stat.S_ISCHR(os.fstat(self.fd).st_mode):
                raise ValueError("device path must be a character device")
            self.original_capacity = self.get_capacity()
            self.fcntl.ioctl(self.fd, self.abi["clear"])
            self.fcntl.ioctl(self.fd, self.abi["set_capacity"], struct.pack("=Q", self.capacity))
        except BaseException as original:
            try:
                self._close()
            except Exception as cleanup:
                raise original from cleanup
            raise
        return self

    def _close(self):
        # Invalidate before close: an error must never trigger a retry on a
        # descriptor number that the OS may already have reused.
        fd, self.fd = self.fd, None
        if fd is not None:
            os.close(fd)

    def __exit__(self, exc_type, exc_value, traceback):
        if self.fd is None:
            return False
        try:
            try:
                self.fcntl.ioctl(self.fd, self.abi["clear"])
                self.fcntl.ioctl(self.fd, self.abi["set_capacity"],
                                 struct.pack("=Q", self.original_capacity))
            finally:
                self._close()
        except Exception as cleanup:
            if exc_value is not None:
                raise exc_value.with_traceback(traceback) from cleanup
            raise
        return False

    def get_capacity(self):
        data = bytearray(8)
        self.fcntl.ioctl(self.fd, self.abi["get_capacity"], data, True)
        return struct.unpack("=Q", data)[0]

    def apply(self, op):
        try:
            kind = op["op"]
            if kind == "read":
                data = os.read(self.fd, op["count"])
                return success(len(data), data)
            if kind == "write":
                return success(os.write(self.fd, bytes.fromhex(op["data"])))
            if kind == "clear":
                self.fcntl.ioctl(self.fd, self.abi["clear"])
                return success()
            if kind == "resize":
                self.fcntl.ioctl(self.fd, self.abi["set_capacity"],
                                 struct.pack("=Q", op["capacity"]))
                return success()
            if kind == "capacity":
                return success(self.get_capacity())
            raise ValueError("unknown operation")
        except OSError as exc:
            if exc.errno in (errno.ENOMEM, errno.EINTR, errno.ENODEV, errno.EIO):
                raise
            return failure(exc.errno)
