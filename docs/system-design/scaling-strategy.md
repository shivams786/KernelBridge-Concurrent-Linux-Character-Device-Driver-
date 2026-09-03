# Scaling Strategy

This project scales differently from a web application. The module runs inside
one kernel instance, so horizontal scaling means running it on multiple hosts or
VMs, not adding more API pods behind a load balancer.

## Current Scale

```text
One VM
One loaded module
One device node
One shared circular buffer
User-space tools and tests
```

## Stage 1 - Local Development

- Build with local kernel headers.
- Load manually with `scripts/load.sh`.
- Test through the CLI and shell integration tests.
- Inspect `dmesg` and ioctl stats.

## Stage 2 - Repeatable VM Testing

- Use a dedicated disposable Ubuntu VM.
- Run `sudo bash tests/run_all_tests.sh`.
- Keep logs from each run.
- Test multiple kernel versions when possible.

## Stage 3 - Managed Host Fleet

If the driver became part of a larger product:

- deploy through packages instead of manual `insmod`
- sign modules where Secure Boot requires it
- collect stats with a user-space agent
- centralize logs and health checks
- track module version per host

## Stage 4 - Larger Architecture

Only if justified:

- management API for host inventory
- telemetry database for stats history
- queue for async report generation
- object storage for test artifacts
- search over logs or host metadata

## Bottleneck Analysis

| Bottleneck | Why it appears | Possible response |
| --- | --- | --- |
| Global mutex | all buffer operations share one lock | per-open buffers, per-CPU stats, finer-grained design |
| 64 KiB cap | intentional memory safety bound | make cap configurable at build time after testing |
| User/kernel copies | every I/O crosses the boundary | larger chunks, mmap design, or hardware/DMA path if justified |
| One device instance | current module registers one minor | allocate multiple minors with per-device contexts |
| Volatile stats | counters reset on unload | user-space telemetry collector |

