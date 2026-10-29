# Senior systems portfolio: evidence before features

This is a virtual byte-stream driver, not a hardware driver or a production
deployment. The work should be presented with that scope. Seniority comes from
the quality of decisions, measurements, and failure handling, not repository size.

## Current assessment

The component has bounded buffering, blocking and nonblocking I/O, poll,
configuration ioctls, operational counters, and integration scripts. Its mutex
protects the buffer during user copies, which simplifies correctness but allows
page faults to extend lock hold time. The existing framed concurrency test uses
userspace read/write locks; it validates integrity but is not an unrestricted
multiwriter contention benchmark. No benchmark numbers or runtime kernel test
results are asserted here.

The hardening pass adds regression coverage for control wakeups and partial
user-copy faults, fixes false EOF after control changes, and accounts for bytes
actually copied before a fault. CI now includes module compilation against
distribution headers on two Ubuntu releases. Compilation does not establish
runtime safety or compatibility with every kernel in those releases.

## Delivery gates

| Priority | Work | Evidence required |
| --- | --- | --- |
| P0 | Run integration suite in disposable Linux VM | Commit ID, kernel config, compiler version, complete logs, clean kernel diagnostics |
| P0 | Add buffer KUnit tests | Wraparound, full/empty, resize preservation, rejected shrink, allocation failure |
| P0 | Debug-kernel validation | Separate KASAN/lockdep and KCSAN runs; concurrent I/O plus clear/resize/mode storms |
| P1 | Reproducible performance harness | Throughput, p50/p95/p99 latency, CPU cost, context switches, raw samples |
| P1 | Compare alternatives | Same workload against pipe, Unix socketpair, and userspace shared ring; explain overhead |
| P1 | ABI compatibility | 32-bit userspace on 64-bit kernel, struct layout assertions, compat ioctl support, malformed commands |
| P1 | True contention testing | Independent readers/writers; byte counts and per-producer checks independent of message atomicity |
| P1 | Failure injection | Bad pointers, interrupted waits, allocation failure, invalid sizes, repeated load/unload |
| P2 | Observability | Tracepoints for wait duration and operation latency; measured overhead when disabled/enabled |
| P2 | Deployment discipline | Restrictive device permissions, supported kernel matrix, release checklist, rollback exercise |

Each gate needs a passing artifact, not just an implementation. Preserve failed
runs and explain the correction. Do not publish fabricated performance gains.

## Benchmark protocol

Use an otherwise idle VM with recorded CPU, RAM, virtualization, kernel config,
compiler, commit, and affinity. Test capacities 256, 4096, and 65536 bytes; I/O
sizes 1, 64, 512, and 4096 bytes; and 1, 2, 4, and 8 producers/consumers.
Record short I/O, EAGAIN, and errors separately. Use monotonic timestamps,
warmup, at least five repeated runs, and fixed-duration measurements. Publish
individual runs and variability. The framed correctness tool's sleep/retry and
userspace mutex costs must not be attributed solely to the driver.

Start with the current mutex implementation. Consider split locking or staging
buffers only after profiling identifies a bottleneck. A lock-free ring needs an
explicit producer/consumer model and memory-order proof; it is not an automatic
upgrade. Do not add mmap without a real workload and a mapping/lifetime/security
contract.

## Architecture discussion

Be ready to defend why this runs in the kernel. For ordinary application IPC,
pipes or Unix sockets are usually the baseline to compare. This project is useful
for exploring a bounded device interface and kernel synchronization; attaching a
real hardware producer would require a separate interrupt/DMA/lifetime design.

Explain byte-stream semantics: writes can be short and frames can interleave
across separate calls. Explain global controls: one process can affect another
process's waits and buffered data. Device permissions therefore belong in the
design, and per-open mode would be a deliberate ABI/product decision.

For an architect interview, bring one design decision, one reproduced failure,
one measurement, and one rejected alternative. Discuss ownership, rollout,
debugging cost, and compatibility alongside implementation details.

## Resume wording

After running the tests, a defensible bullet is:

> Developed a Linux virtual character driver with bounded FIFO buffering,
> blocking/nonblocking I/O, poll readiness, and versioned ioctl statistics;
> added regression coverage for control-wakeup races and user-memory faults,
> with kernel build checks across two Ubuntu environments.

Replace this with measured outcomes when available. Add kernel versions and
benchmark results only after reproducing them. This repository supports a systems
engineering story; it does not by itself demonstrate ten years of architecture
ownership, team leadership, or production impact.

## References

- [Kernel user-copy semantics](https://www.kernel.org/doc./htmldocs/kernel-hacking/routines-copy.html)
- [Kernel ioctl and compatibility guidance](https://docs.kernel.org/driver-api/ioctl.html)
