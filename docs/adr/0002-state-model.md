# ADR 0002: Use In-Kernel Volatile State

## Status

Accepted

## Context

The driver needs to store unread bytes and operational counters. It does not
need durable persistence.

## Decision

Use in-kernel memory for the circular buffer and atomic counters for stats.

## Alternatives

- Persist data in a user-space database.
- Write data to disk from the kernel.
- Add a user-space daemon to mirror stats.

## Consequences

The module remains simple and fast to test. Buffered data and stats disappear
when the module unloads unless a future user-space collector is added.

