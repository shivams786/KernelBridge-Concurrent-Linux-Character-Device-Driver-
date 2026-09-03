# Technical Debt

This file is intentionally honest. The project is useful, but it is not
finished forever.

## Known Limitations

- Only one device instance is registered.
- All file handles share one buffer.
- Buffered data is volatile.
- No sysfs attributes are exposed yet.
- No tracepoints are available yet.
- No package/deb install flow exists.
- Kernel integration tests are not automated in hosted CI.
- The driver does not model real hardware, interrupts, DMA, or bus probing.

## Security Improvements

- Document module signing for Secure Boot systems.
- Consider stricter udev rules for demos on shared machines.
- Add optional fault-injection tests in a VM.
- Add tests for repeated invalid ioctl calls and log rate limiting.

## Scaling Risks

- The single mutex can become a bottleneck under high contention.
- The 64 KiB buffer cap is safe but intentionally small.
- Stats are not durable across unloads.
- One shared buffer makes multi-client isolation impossible.

## Refactoring Opportunities

- Add a user-space test shim for circular-buffer unit tests.
- Split ioctl handling into smaller helper functions if more commands are
  added.
- Add generated docs from the UAPI header if the ABI grows.

## Future Infrastructure

- Privileged VM CI for kernel-module integration tests.
- Release packaging.
- Optional user-space telemetry collector.
- Optional tracepoint-based observability.

