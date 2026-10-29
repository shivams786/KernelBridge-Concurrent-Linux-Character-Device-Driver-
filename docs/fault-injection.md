# Fault-injection evidence and safety

No kernel fault injection was executed on the Windows host. Do not enable
system-wide injection on a shared machine. Linux experiments require a disposable
guest, a snapshot, serial console capture, and an external VM watchdog.

| Mechanism | Expected behavior | Evidence/status |
| --- | --- | --- |
| Simulator false-eof, reverse-read, resize-loss | Bounded checker rejects invalid FIFO behavior | TESTED; 40-run study, all deliberately faulty fixtures detected |
| Simulator worker OSError and cleanup OSError | Cleanup attempted; inconclusive, never pass | TESTED; test_replay.py |
| Synthetic pthread_create EAGAIN at each of four starts | Join only initialized handles, report startup failure | IMPLEMENTED; thread_start_test.c; Linux execution blocked in this session |
| mprotect next page PROT_NONE | Account only transferred bytes, or EFAULT when none | IMPLEMENTED; regression_test.c; Linux blocked |
| SIGUSR1 on blocked reader, no SA_RESTART | EINTR and empty FIFO remains unchanged | IMPLEMENTED this iteration; Linux build/runtime blocked |
| CLEAR/resize/mode during blocked read | Recheck readiness; no false EOF | IMPLEMENTED; Linux blocked |
| Allocation failure during resize/init | ENOMEM, preserve old FIFO / unwind acquired resources | PLANNED experiment; no runtime evidence |

## Bounds and cleanup

Portable reduction limits operation count, checker states, candidate count, and
trial count. Run the study/replay CLI under an external timeout for a hard
wall-clock limit. Worker exception tests finish through the context manager.
The Linux regression is launched by tests/run_all_tests.sh under its timeout;
the outer validation runner attempts module unload and captures diagnostics even
after suite failure. It refuses an already-loaded module to avoid interfering
with an existing user. A failed C CHECK exits the process: the OS closes its
descriptors and mappings, and the outer runner handles module cleanup.

## Allocation failure protocol (not executed)

Use the matching kernel source's `tools/testing/fault-injection/failcmd.sh --help`
and inspect supported fail_page_alloc/failslab controls, task filtering, interval,
probability, times, and GFP filters. Do not assume one failed slab allocation
forces kvmalloc to fail: it may fall back to vmalloc. Restrict injection to the
test task, record every setting before modification, inject a bounded number
of failures, and restore settings in a cleanup trap before unloading the module.
The exact command must be selected for the guest kernel; no untested universal
debugfs recipe is provided. The official [fault-injection documentation](https://www.kernel.org/doc/html/latest/fault-injection/fault-injection.html)
describes supported mechanisms and filters.

Preload known bytes; attempt resize; capture errno/capacity/readback and dmesg;
assert old state on ENOMEM. Test initialization failures separately, verifying
no leaked class, device number, or module. Save before/after configuration and
cleanup result. Do not treat an injection request without a reached allocation
failure as coverage.

## Diagnostics acceptance

KUnit, KASAN, KCSAN, lockdep, UBSAN, and kmemleak: **BLOCKED**, kernel configuration
unknown because the guest cannot boot here. For each future run capture the
actual configuration, workload, command, output, and cleanup. KUnit needs KTAP;
sanitizer coverage needs an enabled kernel and executed workload, not just a
config file. A clean run is evidence for that workload, never a proof of absence
of all races or memory errors.
