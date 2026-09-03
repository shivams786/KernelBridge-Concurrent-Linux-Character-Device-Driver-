# ADR 0001: Keep the Project as a Modular Kernel Driver

## Status

Accepted

## Context

The project is a Linux character-device driver. The request to make it more
production-ready could be misread as adding a web backend, database, cache, and
dashboard.

## Decision

Keep the core architecture as a focused kernel module plus user-space tools and
tests. Improve the surrounding system-design, security, verification, and
operations material.

## Alternatives

- Build a separate web management app.
- Split the code into artificial services.
- Add a user-space daemon before there is a real need.

## Consequences

The project stays coherent and runnable in a VM. It does not pretend to solve
unrelated SaaS problems.

