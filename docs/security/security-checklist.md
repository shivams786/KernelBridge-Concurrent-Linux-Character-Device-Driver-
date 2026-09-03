# Security Checklist

## Kernel Boundary

- [x] User pointers copied with kernel helpers.
- [x] Ioctl magic and command numbers validated.
- [x] Ioctl structures use fixed-width types.
- [x] Stats structure is zeroed before returning to user space.
- [x] Kernel pointers are not exposed.
- [x] Buffer capacity is bounded.
- [x] Resize cannot silently drop unread data.

## Concurrency

- [x] Shared buffer state protected by a mutex.
- [x] Blocking paths drop the mutex before sleeping.
- [x] Wait conditions are rechecked after wakeup.
- [x] Readers and writers are woken after state changes.

## Operations

- [x] Load script verifies module and device node.
- [x] Unload script checks for processes holding the device when possible.
- [x] Tests use timeouts.
- [x] Tests scan `dmesg` for serious kernel failures.

## Remaining Hardening

- [ ] Add optional sysfs read-only attributes.
- [ ] Add tracepoints for high-signal events.
- [ ] Add module signing documentation for Secure Boot systems.
- [ ] Add package-based install/uninstall flow.
- [ ] Add privileged self-hosted CI or VM automation for integration tests.

