# Caching Strategy

The current project does not use Redis or an application cache. That is a
deliberate choice.

## Current State

The circular buffer is not a cache. It is the device's primary volatile data
store. Treating it as a cache would be misleading because reads consume data
and clear removes data.

## Why No Redis

Redis would not help the kernel module directly:

- kernel code should not depend on a user-space Redis server
- the data path is local to one kernel instance
- the buffer size is intentionally small
- there is no expensive query or dashboard aggregate to cache

## Future Cache Use

If a user-space management daemon is added later, caching may make sense for:

- sampled stats dashboards
- repeated module metadata lookups
- expensive historical reports
- per-host health summaries

Possible key shapes:

```text
host:{hostId}:module:{moduleName}:latest-stats
host:{hostId}:module:{moduleName}:health
release:{version}:compatibility
```

## TTL and Invalidation

Operational stats should use short TTLs, for example 5 to 30 seconds. Release
metadata can use longer TTLs. Any control-plane action such as resize, mode
change, load, or unload should invalidate the affected host/module keys.

## Stale Data

Stale stats are acceptable for dashboards, but not for control decisions. Any
future management API should read directly from the device before applying a
dangerous action.

