# ADR 0003: Do Not Add Redis or External Caching Yet

## Status

Accepted

## Context

The current data path is local to one kernel instance and has no expensive
queries or durable dashboards.

## Decision

Do not add Redis or another cache. Document future cache use only for a possible
management daemon or telemetry system.

## Alternatives

- Add Redis for stats.
- Add a local daemon with an in-memory cache.

## Consequences

The project avoids unnecessary infrastructure. If telemetry is added later, it
can introduce caching at the user-space service layer.

