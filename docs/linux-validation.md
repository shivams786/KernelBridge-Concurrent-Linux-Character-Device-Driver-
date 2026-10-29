# Linux validation with evidence

The driver still needs actual Linux runtime validation. A Windows simulation,
successful Python tests, or compilation against unrelated kernel headers does
not establish that the module runs correctly.

## Current host status: 2026-10-25

WSL lists Ubuntu as Installing. Attempting to execute uname in that distribution
returns WSL_E_DISTRO_NOT_FOUND. The incomplete installation was not modified.
Complete Ubuntu provisioning or use a disposable Linux VM before runtime tests.
WSL also requires build headers matching its own running kernel; Ubuntu's
generic kernel headers do not substitute for WSL kernel headers.

## Prepare a disposable Ubuntu/Debian guest

Copy or clone the project into the guest, then run:

```sh
sudo bash scripts/setup.sh --install --yes
python3 -m lab.validate_linux --output artifacts/linux-build
sudo python3 -m lab.validate_linux --integration --output artifacts/linux-runtime
```

Use Python 3.10 or later and a kernel with module loading enabled. The first
validation command only builds and checks userspace/kernel artifacts; it does
not load a module. The integration flag explicitly permits load/unload of
ringbuf_char and requires root. The runner refuses an already-loaded module.
Do not use a shared or production machine: the tests control the shared device
and discard buffered data. Secure Boot or module-loading policy may require
additional guest configuration; a load rejection is a failure, not a skip.

## What the runner records

The runner uses git ls-files to collect tracked and nonignored untracked files,
including local modifications. It builds a temporary source snapshot under
/tmp/kernelbridge-* so Kbuild receives a path without spaces. Shell CRLF endings
are normalized in the snapshot only, with both original and build hashes saved.
Symlinks and paths outside the source tree are rejected. Ignored local helper
files are not included. The original checkout is not cleaned or rewritten.

Each evidence directory contains a manifest, build-source.tar.gz, source hashes,
compiler output, per-stage logs, the built .ko and its hash, vermagic output,
and kernel configuration when readable. Config unavailability is recorded as
null rather than claimed as captured. The hash is checked again after the tests
to detect module changes during execution.

Integration runs additionally preserve the individual suite logs, sequential
and concurrent contract evidence, full before/after dmesg snapshots, cleanup
results, and kernel diagnostic findings. The runner checks for kernel warnings,
oopses, sanitizer reports, and panics. If the log prefix changes or rolls over,
diagnostic coverage is inconclusive and the overall validation does not pass.
Unrelated kernel warnings can fail the run; inspect the retained logs rather
than silently suppressing them.

## Result interpretation

- passed / build-only: builds and startup/shell checks passed; runtime_validated=false
- passed / build-and-integration: suite exit, module cleanup, identity, and diagnostics passed
- blocked: missing Linux environment, matching headers, privileges, or required tools
- failed: build/test failure, timeout, cleanup failure, or incomplete diagnostic evidence
- running: interrupted or still active; never treat as passed

Exit codes are 0 for passed, 1 for failed, and 2 for blocked/invalid invocation.
The output directory must be new. Logs are written directly while stages run;
step status is saved after each stage. On a timeout, POSIX child process groups
are terminated, then module cleanup is attempted. A kernel task stuck in
uninterruptible sleep can resist process termination; use an external VM
watchdog/reset for that case. Python-level timeouts cannot recover a hung kernel.

These checks do not execute KUnit or prove KASAN, KCSAN, or lockdep coverage.
Run the KUnit instructions in validation-milestone.md on an appropriately
configured kernel and retain its KTAP results separately. No CI job is considered
executed merely because its configuration exists in the repository.
