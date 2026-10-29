# Performance decision record

The full workload, raw-sample format, and commands remain in
[benchmarking.md](benchmarking.md); this note records the current decision.

Linux device baseline: **BLOCKED** on a runnable guest and matching headers.
No kernel optimization was accepted. The existing Windows pipe/socket results
are harness/host measurements, not ringbuf_char throughput or kernel-only time.

`lab/benchmark.py` measures Python write/read round trips, including interpreter,
syscall, transport, and scheduling overhead. Logical throughput counts payload
once, not both write and read bytes. Report per-repeat distributions and raw
samples; the median of repeat p99s is not a pooled p99. CPU process time does
not isolate kernel cost. The C concurrency test serializes same-side framed
traffic and is not a mutex-contention benchmark.

Acceptance sequence: validate correctness on the guest; record kernel/module
hashes, CPU, affinity, capacity, payload, warmup, repetitions, and diagnostics;
run identical pipe/socket/device workloads; retain failures separately; profile
the measured bottleneck; only then compare a proposed change against baseline.
Separate blocking and nonblocking workloads, contention from single-process
round trips, and control-plane resize activity from steady-state transfer.

A native C benchmark is deferred, not implemented for appearance. Add one if
profiling shows Python overhead masks the question of interest. It must retain
partial-I/O/error handling and raw samples with the same payload accounting.
No improvement is claimed without repeated before/after measurements and
correctness regressions. Median/range results from the reducer experiment are
tooling measurements, not device-performance results.
