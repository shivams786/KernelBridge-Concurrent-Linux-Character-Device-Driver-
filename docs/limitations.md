# Current limitations

Status as of 2026-10-25. The project is not fully validated or production-ready.

- WSL Ubuntu remains Installing; execution returns WSL_E_DISTRO_NOT_FOUND.
  No kernel build/load, KUnit, sanitizers, allocation injection, or Linux device
  benchmark ran in this session. CI files are configuration, not execution proof.
- One shared virtual device; no hardware, IRQ, DMA, bus, hotplug, or isolation.
- Single mutex includes user-copy and resize allocation; no fairness guarantee.
  O_NONBLOCK avoids readiness waiting, not every source of latency.
- Native ABI only; 32-bit compat dispatch is not implemented or verified.
- Counters are approximate; global controls can affect every client.
- Contract checker covers only five nonblocking operations, <=12 concurrent
  calls, finite search budget. It is not formal verification of the driver.
- Concurrent reduction CLI is simulation-only. Barrier starts do not control
  kernel scheduling. A contract-failure signature is not a root-cause signature.
- Fixture outcomes demonstrate checker/reducer behavior, not discovered kernel
  races. No novel algorithm or production deployment is claimed.
- Python worker threads cannot forcibly terminate a wedged syscall. Use an
  external process timeout and a disposable VM watchdog for real kernel tests.
- Evidence hashes identify input bytes; they are not cryptographic attestation.
  Local artifacts are ignored by Git and must be retained separately for review.

The phase acceptance ledger is in [execution-status.md](execution-status.md).
