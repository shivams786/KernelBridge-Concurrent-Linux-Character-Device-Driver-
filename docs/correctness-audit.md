# Correctness audit

Reviewed 2026-10-25 against the dirty working tree based on commit 152dacd.
Evidence class: STATIC ANALYSIS (manual source review), with portable regression
tests where noted. This is not a clean kernel sanitizer or compilation report.

## Highest-priority risks

1. No runnable Linux guest: module build, load, regressions, and diagnostics are
   acceptance blockers, not inferred from Python tests.
2. Offline history rechecking could turn a cleanup failure into a passing
   verdict. Fixed by requiring a matching execution result without an error;
   the cleanup-failure regression passes. Search-budget exhaustion may still be
   rechecked with a larger budget.
3. Copying user memory under the single mutex can stall every device caller.
   Correctness favors the simple lock today; latency/fault behavior needs Linux
   measurement before attempting a staged-copy redesign.
4. The wait predicates read buffer fields without the mutex. READ_ONCE and the
   generation counter support rechecking, but stress testing and KCSAN evidence
   are missing. A predicate is only a wakeup hint, never authorization to copy.
5. Global controls are available to all openers; untrusted multi-client use can
   destroy data or change blocking policy. Restrict device permissions, do not
   market this as an isolated service.

## Source review matrix

| Area | Observation / disposition |
| --- | --- |
| Allocation | kzalloc device, kvmalloc buffer; reverse-order error labels free acquired resources. Allocation-failure execution remains blocked. |
| Publication | cdev_add precedes class/device creation. Publication/error-unwind races have not been stress-tested; no unproven UAF claim is made. |
| Lifetime | file_operations.owner and cdev.owner set; open stores context; release decrements handle count. Forced unload unsupported. |
| FIFO bounds | span helpers bound copies, consume/commit clamp counts; resize rejects undersized capacity before allocation. KUnit coverage exists but has not run here. |
| Locking | One mutex serializes buffer mutation and controls; wait releases lock and retries. Sleeping user-copy/allocation is allowed with mutex, not spinlock. |
| Wakeups | Data writes wake readers; reads wake writers; controls increment generation and wake both. Prior false-EOF-on-control fix is present; Linux regression pending. |
| User-copy | Only copied prefix is consumed/committed. Prior partial-copy fix present; mprotect-based Linux regression pending. |
| Signals | Read/write use interruptible mutex/waits. Added SIGUSR1 interrupted-read test without SA_RESTART; not compiled/run here. |
| Poll | Registers wait queues before locked state snapshot; readiness is not a reservation. Existing integration suite pending. |
| Counters | Individual atomics, not a coherent transaction. Excluded from strict linearizability observations. |
| Ioctl | Full command switch after magic/number check; reserved stats zeroed; fixed-width fields. Added compile-time v1 layout assertions; compilation pending. |
| Logging | SET_MODE/SET_CAPACITY logged every call. Changed to pr_info_ratelimited to bound log spam from permitted callers; kernel verification pending. |
| Compatibility | No compat_ioctl. No 32-bit-on-64-bit runtime claim; do not add a handler without target-architecture tests. |
| Harness cleanup | Simulator worker/cleanup exceptions remain inconclusive. Regression confirms cleanup attempted once and no passing recheck. |

## Regression acceptance

Portable tests: `python3 -m unittest discover -s tests -p 'test_*.py' -v`.
The follow-up capture-validation regressions reproduced three false acceptances
(changed worker ownership, changed explicit worker plan, and unknown inconclusive
reason) plus a malformed-event traceback before the fix. Offline rechecking now
checks saved program order and permits inconclusive reconsideration only for
search-budget exhaustion. The complete portable suite passes 59 tests; logs are
in `artifacts/capture-validation-20261025/`.

Linux acceptance: run the snapshot workflow in [linux-validation.md](linux-validation.md).
The signal regression runs under the suite's external timeout; a hung kernel
still requires a disposable-VM watchdog. The log-rate change is source-reviewed,
not backed by a runtime rate assertion. No ABI numbers or locking architecture
were changed. New work does not replace or revert earlier dirty changes.
