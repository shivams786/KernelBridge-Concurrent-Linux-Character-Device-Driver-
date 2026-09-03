# Capacity Planning

The current driver is intentionally small. The capacity plan is based on a
single Ubuntu VM running local tests, not a distributed service.

## Assumptions

| Metric | Assumption |
| --- | --- |
| Device instances | 1 |
| Concurrent processes | 1 to 32 in normal demos |
| Stress-test threads | 4 to 64 |
| Buffer capacity | 256 B to 65536 B |
| Typical message size | 64 B to 4096 B |
| Read/write ratio | roughly 1:1 in concurrency tests |
| Persistence | none |
| Daily traffic | not applicable unless a test harness runs continuously |

## Memory Use

The main variable memory cost is the circular buffer:

```text
buffer memory = configured capacity
minimum       = 256 bytes
default       = 4096 bytes
maximum       = 65536 bytes
```

The driver context, wait queues, cdev, and counters are small compared with the
maximum buffer.

## I/O Throughput

Throughput depends mostly on:

- user/kernel copy cost
- mutex contention
- scheduler behavior under blocking tests
- VM performance
- read/write chunk size

The concurrency test reports measured throughput rather than claiming a fixed
number.

## Growth Limits

The current design is healthy for a learning and demonstration driver. It is
not designed for very large buffers, durable storage, or high-frequency
multi-producer telemetry.

If the use case grows, the first bottlenecks are likely:

- one global mutex around the shared buffer
- one shared buffer for all file handles
- lack of per-device instances
- lack of durable telemetry

