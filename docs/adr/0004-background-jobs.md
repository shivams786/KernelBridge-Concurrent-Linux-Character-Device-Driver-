# ADR 0004: Keep Background Jobs Out of the Kernel Module

## Status

Accepted

## Context

The request mentions queues, workers, retries, and scheduled jobs. Those are
useful in application services, but the kernel module should not own email,
report generation, or external integrations.

## Decision

Keep background processing out of the kernel module. If future reporting or
telemetry needs async work, implement it in a user-space worker process.

## Alternatives

- Add kernel threads for periodic work.
- Add a user-space worker immediately.

## Consequences

The current module stays small. Future background work has a clear place:
outside the kernel, reading stats through the ABI.

