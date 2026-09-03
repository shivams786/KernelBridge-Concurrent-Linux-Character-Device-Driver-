# Testing

These tests are meant to run in a disposable Linux VM, not on a daily-use host:

```sh
make
sudo bash tests/run_all_tests.sh
```

The suite loads and unloads a real kernel module, so root is required. Each
test has a timeout because a driver bug can otherwise leave a shell sitting
forever on a blocked read or write.

## What Each Test Covers

| Test | What I expect it to catch |
| --- | --- |
| `test_basic.sh` | Device node creation, normal open/close, simple write/read, zero-length I/O |
| `test_ioctl.sh` | Capacity queries, resize, stats, reset-stats, clear, invalid resize, unsupported ioctl |
| `test_nonblocking.sh` | `EAGAIN` on empty non-blocking read and full non-blocking write |
| `test_poll.sh` | Read readiness after a delayed writer and write readiness when space exists |
| `test_concurrency.sh` | Deadlocks, stream corruption, broken partial I/O handling, suspicious kernel logs |
| `run_all_tests.sh` | Deterministic ordering, log capture, cleanup trap, final `dmesg` scan |

## Feature Mapping

| Feature | Covered by |
| --- | --- |
| Dynamic device registration | `scripts/load.sh`, `test_basic.sh` |
| Shared ioctl header | user-space build plus ioctl tests |
| Buffer clear | `test_basic.sh`, `test_ioctl.sh` |
| Stats ioctl | `test_ioctl.sh`, `scripts/inspect.sh` |
| Capacity resize | `test_ioctl.sh` |
| Resize below unread data | `test_ioctl.sh` |
| Non-blocking read/write | `test_nonblocking.sh` |
| Poll readiness | `test_poll.sh` |
| Concurrent readers/writers | `test_concurrency.sh`, `userspace/concurrent_test.c` |
| Stream-safe validation | framed messages in `concurrent_test.c` |
| Kernel log health | `test_concurrency.sh`, `run_all_tests.sh` |

## Notes on the Concurrency Test

The concurrency test does not assume that one `read()` equals one `write()`.
That would be wrong for a stream device. Writers emit framed messages with a
magic value, writer id, sequence number, payload length, and checksum. Readers
append whatever bytes they get into a shared parser and validate complete
frames as they appear.

The test is still a stress test, not a proof. It is useful because it shakes
the read/write paths and catches obvious corruption, missed wakeups, and hangs.

## Optional Local Checks

Use these when the tools are installed:

```sh
make shellcheck
make cppcheck
make sparse
make C=1 module
cd userspace && make asan
valgrind ./ringbuf_char_client stats
```

GitHub Actions only builds the user-space programs and runs static checks that
make sense on a hosted runner. Loading the kernel module belongs in a
privileged VM.

