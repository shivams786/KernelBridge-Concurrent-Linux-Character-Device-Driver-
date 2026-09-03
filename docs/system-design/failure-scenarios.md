# Failure Scenarios

## Missing Kernel Headers

Effect: `make module` cannot build.

Detection: top-level `Makefile` checks `/lib/modules/$(uname -r)/build`.

Fallback: install matching headers with `sudo apt install linux-headers-$(uname -r)`.

Prevention: run `bash scripts/setup.sh` before building.

## Module Load Failure

Effect: `/dev/ringbuf_char` is not created.

Detection: `scripts/load.sh` checks `lsmod` and waits for the device node.

Fallback: inspect `dmesg`, rebuild, and retry.

Prevention: validate module parameters and keep initialization cleanup paths
complete.

## Invalid Module Parameter

Effect: module init returns `-EINVAL`.

Detection: `dmesg` contains a `ringbuf_char:` error explaining the allowed
capacity range.

Fallback: reload with a capacity between 256 and 65536.

Prevention: keep parameter validation early in module init.

## User Pointer Fault

Effect: read or write returns `-EFAULT`, or returns a partial count if some
bytes were already copied.

Detection: CLI prints `errno`; driver increments failed-operation stats and
logs a rate-limited warning.

Fallback: caller fixes the invalid buffer.

Prevention: use `copy_to_user` and `copy_from_user`; never dereference user
pointers directly.

## Full Buffer

Effect: blocking writers wait; non-blocking writers receive `EAGAIN`.

Detection: ioctl stats show stored bytes near capacity and blocked writes.

Fallback: readers drain data, or an operator clears/resizes the buffer.

Prevention: tests cover full-buffer non-blocking behavior.

## Empty Buffer

Effect: blocking readers wait; non-blocking readers receive `EAGAIN`.

Detection: stats show stored bytes at zero and blocked reads.

Fallback: writers add data, or a control operation wakes waiters.

Prevention: tests cover empty-buffer non-blocking behavior and poll behavior.

## Busy Module During Unload

Effect: `rmmod` fails.

Detection: `scripts/unload.sh` checks processes holding `/dev/ringbuf_char` with
`fuser` when available.

Fallback: close the process file descriptors and retry.

Prevention: `.owner = THIS_MODULE` is set in `file_operations`.

## Worker or Test Harness Hang

Effect: shell test does not complete.

Detection: tests use `timeout`; `run_all_tests.sh` reports failure.

Fallback: unload the module, inspect `dmesg`, and rerun with `debug=1`.

Prevention: keep blocking paths structured around wait queues and state
rechecks.

## Kernel Warning or Oops

Effect: VM may become unstable.

Detection: integration tests scan `dmesg` for `BUG`, `WARNING`, `Oops`,
`panic`, `use-after-free`, and `invalid opcode`.

Fallback: reboot or revert the VM snapshot.

Prevention: run in disposable VMs, keep buffer bounds tight, and use kernel
copy helpers.

