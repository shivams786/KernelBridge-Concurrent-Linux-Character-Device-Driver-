# Device contract

This is the source-level contract of ABI v1, not a claim of Linux runtime
verification. The executable model is `lab/contract.py`; the independent deque
fixture is `lab/backends.py`. They intentionally cover only a subset below.

## State and operations

There is one shared byte FIFO, not one buffer per descriptor. Capacity is
256..65536 bytes (4096 by default). The FIFO starts empty. No record boundaries,
message atomicity between separate syscalls, or fairness guarantee is provided.

| Operation | Required result |
| --- | --- |
| read(0), write(empty) | Return zero, no FIFO change |
| nonempty read with data | Return the available prefix, at most the request |
| nonempty write with space | Append the fitting prefix, return its length |
| nonempty read on empty / write on full | EAGAIN in nonblocking mode; otherwise wait interruptibly |
| CLEAR | Discard all bytes; wake both queues; not EOF |
| SET_CAPACITY | Preserve FIFO order; EINVAL outside bounds; EMSGSIZE below occupancy; ENOMEM on allocation failure with old state retained |
| GET_CAPACITY | Copy an unsigned 64-bit capacity to userspace |
| SET_MODE | Accept only NONBLOCK bit; unknown bits EINVAL; wake both queues |
| GET_STATS | Zero-initialized v1 structure; buffer fields coherent under mutex, counters approximate |
| RESET_STATS | Reset event totals, not current open handles or FIFO; not an atomic multi-counter epoch |
| unsupported ioctl | ENOTTY, including wrong encoded size/direction |
| bad ioctl pointer | EFAULT |
| seek | Unsupported (`no_llseek`) |

The lab normalizes GET_CAPACITY into `ret=capacity`; the actual ioctl returns 0
and copies capacity through its pointer. Errors normalize to `ret=-1, errno=n`.
Successful reads include canonical lowercase hexadecimal bytes in `data`.

## Partial faults, blocking, and readiness

Read/write commit only `requested_chunk - uncopied_bytes` from user-copy calls.
If any bytes moved, return that positive count, including across wraparound.
If none moved, return EFAULT. A bad write pointer must not commit zero-filled
uncopied bytes. The generic model assumes accessible memory and does not model
partial faults; `userspace/regression_test.c` exercises them on Linux.

Effective nonblocking mode is descriptor O_NONBLOCK OR global NONBLOCK. This
means do not wait for FIFO readiness, not wait-free execution: mutex acquisition,
allocation, and page faults may still sleep. A signal during interruptible wait
returns the kernel restart code; userspace sees EINTR or a restarted syscall
depending on signal disposition. The regression uses no SA_RESTART.

poll registers both queues before checking state under the mutex. Data means
POLLIN/POLLRDNORM; free space means POLLOUT/POLLWRNORM. Readiness is a snapshot,
not a reservation. Another caller may consume it before the next syscall.
Shutdown branches are defensive; normal module references prevent unloading
while descriptors remain open. Forced unload is not a supported use case.

## Access and ABI limits

Device-node permissions are the access boundary. Any opener can issue controls,
even through a read-only descriptor. There is no per-client isolation or admin
capability check. Tests need exclusive, disposable-device use, and destroy data.

`ringbuf_char_stats` contains two u32 fields, fifteen u64 fields, and two u32
fields: 136 bytes, capacity at offset 8, mode at 128, reserved at 132.
`abi_dump.c` contains compile-time layout/direction assertions. Source inspection
is not cross-architecture compilation. No compat_ioctl handler exists; 32-bit
userspace on a 64-bit kernel is not supported/verified by this project.
Keep existing ioctl numbers/layout fixed; use a new command for an incompatible
extension. Reserved output is zeroed, not uninitialized kernel data.

## Executable scope

The Python contract covers read, write, clear, resize, and capacity in
nonblocking mode with transfers <=4096 bytes. It excludes mode transitions,
poll, signals, user faults, statistics, module lifetime, and allocation failure.
Those require separate integration tests. Passing bounded histories proves only
that the observed results admit a legal ordering for this declared model.
