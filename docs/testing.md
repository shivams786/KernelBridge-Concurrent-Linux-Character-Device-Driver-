# Testing

Run the full suite inside a disposable Ubuntu VM:

```sh
make
sudo bash tests/run_all_tests.sh
```

The tests load a real kernel module and should not be run on an important host.

## Feature Matrix

| Feature | Coverage |
| --- | --- |
| Dynamic device registration | `test_basic.sh`, `load.sh` checks `lsmod` and `/dev/shivam_char` |
| Open and release | `test_basic.sh` opens and closes the device directly |
| Write and read | `test_basic.sh` writes known text and compares exact bytes |
| Zero-length I/O | `test_basic.sh` checks zero-length read and write |
| Clear ioctl | `test_basic.sh`, `test_ioctl.sh` |
| Stats ioctl | `test_ioctl.sh`, `inspect.sh` |
| Capacity get/set ioctl | `test_ioctl.sh` |
| Resize preserving data policy | `test_ioctl.sh` rejects resize below unread data |
| Invalid resize | `test_ioctl.sh` |
| Unsupported ioctl | `test_ioctl.sh` |
| Non-blocking empty read | `test_nonblocking.sh` expects `EAGAIN` |
| Non-blocking full write | `test_nonblocking.sh` fills the buffer and expects `EAGAIN` |
| Recovery after full buffer | `test_nonblocking.sh` reads data and writes again |
| Poll readable readiness | `test_poll.sh` waits for a delayed writer |
| Poll writable readiness | `test_poll.sh` verifies a non-full buffer is writable |
| Concurrent readers/writers | `test_concurrency.sh` runs `userspace/concurrent_test` |
| Stream-safe validation | `concurrent_test.c` reconstructs framed messages from byte chunks |
| Kernel log health | `test_concurrency.sh` and `run_all_tests.sh` scan `dmesg` |

## Optional Checks

These commands are useful when tools are available:

```sh
make shellcheck
make cppcheck
make sparse
make C=1 module
cd userspace && make asan
valgrind ./shivam_char_client stats
```

GitHub Actions builds only the user-space programs and static-checks shell/C
code. Hosted CI should not pretend to load privileged kernel modules.
