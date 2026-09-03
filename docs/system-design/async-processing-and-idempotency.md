# Async Processing and Idempotency

## Current Design

The kernel module does not use background jobs, queues, or schedulers. All
device operations are synchronous VFS callbacks.

That is the right default. Kernel code should stay focused on device behavior,
not email, report generation, dashboards, or external integrations.

## Where Async Work Would Belong

If the project grows, async work should live in user space:

```text
Driver stats ioctl
  -> telemetry collector
  -> queue
  -> worker
  -> metrics store / report artifact
```

Possible async jobs:

- collect stats from multiple hosts
- generate test reports
- upload logs from VM runs
- index release notes
- produce benchmark summaries

## Retry Strategy

Future workers should use:

- bounded retries
- exponential backoff
- dead-letter storage for repeated failures
- timeout per job
- structured failure logs

## Idempotency

Current device operations are not idempotent:

- `read` consumes bytes
- `write` appends bytes
- `clear` removes buffered data
- `reset-stats` changes counters

That is normal for a character device. User-space tooling should not blindly
retry mutating operations unless it understands the effect.

Future async jobs should use idempotency keys for:

- uploading the same test log
- importing benchmark results
- processing the same telemetry batch
- generating a report for the same run id

## Clean Shutdown

The module unload path wakes waiters and relies on normal module ownership to
prevent unload while file handles are open. A future user-space worker should
also handle `SIGTERM`, finish or abandon in-flight jobs safely, flush logs, and
close file descriptors.

