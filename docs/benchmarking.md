# Round-trip benchmark protocol

This harness measures a single process writing a payload and reading it back.
It compares anonymous pipes, socket pairs, and ringbuf_char using the same
Python measurement loop. It is an initial end-to-end baseline, not a saturation
throughput benchmark or a measurement of kernel execution time alone.

## Baselines without a driver

```sh
python3 -m lab.benchmark --backends pipe socketpair --sizes 1 64 256 --iterations 5000 --warmup 200 --repeats 5 --output artifacts/baselines
```

Each job uses fresh descriptors and completes warmup before measurement. Job
order is shuffled with a saved seed to reduce fixed-order bias. Socket family is
recorded for every run: Windows may use a loopback AF_INET socket pair rather
than AF_UNIX. Do not compare Windows results with Linux driver results.

## Linux comparison

Use an idle disposable VM with the module loaded and the ABI helper built:

```sh
make userspace
sudo timeout 120 python3 -m lab.benchmark --backends pipe socketpair device --exclusive --sizes 1 64 256 4096 --capacity 4096 --iterations 5000 --warmup 200 --repeats 5 --output artifacts/linux-comparison
```

The device flag acknowledges buffer destruction. Ensure no other process is
using the device. Capacity is restored and data cleared on ordinary exit; forced
termination can skip cleanup, requiring module reload or VM reset. All transports
use nonblocking I/O. EAGAIN is an inconclusive run, not an unbounded retry loop.
External timeout remains necessary for unexpected kernel hangs.

Payloads are 1..4096 bytes and must fit the configured device capacity. Larger
transfers or concurrent producer/consumer workloads need a separate harness.
For pipes/sockets, effective buffer sizes are OS-controlled and are not equalized
to the driver's capacity. No capacity-equivalence claim is implied.

## Metrics and artifacts

- samples.csv: raw per-round-trip nanoseconds, backend, size, repeat, run index
- run-NNN.json: transport identity, status, per-run distribution, counters
- summary.json: completed/attempted repeats and median/min/max throughput
- manifest.json: randomized order, parameters, platform, Python, CPU affinity
  where available, clock resolution, Git state, and Python source hashes

Per-run p50/p95/p99 use nearest-rank percentiles without interpolation. Summary
p99 is explicitly the median of per-repeat p99 values, not a pooled percentile.
Logical MiB/s counts each payload once, although the payload crosses the API
boundary twice. Its denominator is the entire measured loop, including payload
construction, validation, clock calls, and Python bookkeeping. Round-trip samples
time exchange plus Python call/loop/allocation overhead, excluding payload
construction and equality checking. Warmup, setup, and CSV export are excluded.

Short transfers are completed and counted. Every round trip checks payload
integrity. Corruption, EOF, zero progress, unavailable devices, and setup/cleanup
errors invalidate the repeat; they are saved as inconclusive with no performance
measurement. Partial samples from an aborted repeat are not published. Failed
repeats remain visible in attempted counts and never enter median calculations.
Exit 0 means all repeats completed; exit 2 means at least one was inconclusive
or invocation was invalid. Interrupted captures remain marked running.

CPU time is process CPU time. On platforms with resource.getrusage, context
switch deltas are recorded. Peak RSS is the process lifetime high-water mark,
not an allocation delta for this repeat. Missing counters are null, not zero.
The collector does not disable GC, pin CPUs, change priorities, or tune kernels.
No clock-overhead subtraction is performed.

## Local baseline evidence: 2026-10-12

The Windows development-host run completed 30 repeats (two backends, three
payload sizes, five repeats), with 5,000 timed iterations and 200 warmup
iterations per repeat. Raw evidence is in
artifacts/windows-baselines-20261012. The socket transport reported AF_INET.
All 38 Python tests passed, including actual baseline I/O, corruption detection,
short-transfer handling, output checks, and socket setup-timeout restoration.

For 64-byte payloads, median logical throughput was 25.47 MiB/s for the pipe
and 12.55 MiB/s for the AF_INET socket pair. The median of per-repeat p99
round-trip times was 5.0 us and 6.1 us respectively. Throughput ranges were
20.44..27.87 and 5.55..13.29 MiB/s: variability matters and these are short
instrumented runs. They establish that the measurement pipeline works on this
host, not a Linux transport ranking or driver performance result.

Windows loopback setup was blocked in the execution sandbox; the successful
tests and baseline measurement ran outside that sandbox. Socket-pair setup now
has a two-second timeout and restores the process default before measurement.
Run this single-process CLI independently of other Python threads that create
sockets, since setup temporarily changes the default socket timeout.

## What a defensible claim requires

Compare all backends in the same invocation on the same Linux kernel, machine,
Python build, and affinity. Preserve individual runs and inspect variability.
Record VM resources, host load, kernel configuration, compiler, and loaded-module
hash alongside the artifacts; source hashes do not identify a loaded binary.
Repeat on another day or machine before generalizing. Device correctness tests
must pass independently of these measurements.

Follow-on work is a native C harness, controlled independent producers/consumers,
long fixed-duration runs, scheduler/lock profiling, and debug-kernel validation.
Do not describe a Python round-trip speed difference as an optimized driver or
a universal IPC improvement.
