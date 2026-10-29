# V2 engineering audit

Report date: 2026-10-27. Base revision: 152dacd with preserved uncommitted work.
No AGENTS.md was found in the project-tree scan. The existing kernel, UAPI,
checker, reducer, Linux runner, benchmark and prior artifacts were inspected.
An independent baseline run passed all 64 tests; see artifacts/v2-baseline.

## Concrete findings

| Finding and source location | Effect | Disposition |
| --- | --- | --- |
| `lab/backends.py:LinuxDevice`, descriptor lifecycle | Exit left a stale descriptor number; repeated exit could issue ioctls or close against a reused number. Cleanup failures could obscure setup/workload errors. | FIXED in the 2026-10-29 follow-up: invalidate before close, make repeated exit harmless, and preserve the primary error with cleanup as its cause. Five mocked regressions in tests/test_backends.py; no device execution claim. |
| `lab/replay.py:reduce_concurrent`, replay_success_rate | Previously divided all final FAIL results by trials, even when the failure signature did not match. Could report 100% reproduction alongside a rejected reproducer. | FIXED: rate uses matched_failures. Focused wrong-signature regression. |
| `lab/concurrency.py:evaluate_concurrent`, worker exception boundary | Unexpected TypeError escaped the selected exception tuple and lost structured failure evidence. | FIXED: ordinary Exceptions are captured per worker; BaseException cancellation is not swallowed. Regression injects TypeError. |
| `lab/concurrency.py:evaluate_concurrent`, checker call | A malformed backend result could raise instead of producing an inconclusive capture. | FIXED: validation errors become INVALID_CAPTURE with the error and retained history. Regression returns None. |
| `userspace/regression_test.c:interrupted_write` | Interrupted blocking write had no symmetric regression to the existing interrupted read. | IMPLEMENTED, not compiled/run here. Fill FIFO, observe blocked_writes, send SIGUSR1 without SA_RESTART, require EINTR and unchanged occupancy. |
| `lab/benchmark.py:Transport`, setup/exit cleanup | The first endpoint close error skipped the remaining endpoint; on setup failure it also replaced the primary exception. | FIXED in the 2026-10-27 follow-up using ExitStack, clearing callbacks before cleanup and preserving the original setup exception with its cleanup cause. Two regression tests reproduced the defects before the fix. |

The harness fixes are portable correctness changes, not kernel bug
discoveries. Test implementation is in tests/test_v2.py. The previous source
snapshot and worker-plan fixes remain in place.

## Kernel review

Buffer invariants remain: 0 <= len <= capacity, positions inside the allocation,
and span lengths bounded by occupancy/free space and allocation end. Buffer
helpers clamp consume/commit counts. Resize rejects shrink below occupancy and
keeps old state until replacement allocation succeeds. Runtime failure injection
is still required to verify these paths.

`kernel/ringbuf_char.c` uses one mutex around FIFO/control mutations. Read/write
drop it before wait_event_interruptible and recheck after wakeup. Generation
changes wake control-sensitive waiters. READ_ONCE wait predicates are hints, not
permission to copy; KCSAN stress remains an open gate. Partial user copies commit
only the transferred prefix at the read/write copy loops. The mutex may be held
while user memory faults, so latency can be unbounded by the FIFO contract.

poll registers both queues before a locked snapshot; readiness is not reserved.
O_NONBLOCK avoids waiting for data/space, not mutex/page-fault latency. Statistics
are individual atomics, not a coherent multi-counter epoch. They are excluded
from the strict model. Initialization has reverse-order unwind; publication and
allocation failure paths are source-reviewed, not execution-verified.

UAPI v1 layout assertions remain in abi_dump.c. There is no compat_ioctl handler.
Normal module ownership prevents unload with open files; forced unload is not
supported. Controls affect all clients and are authorized by node permissions,
not per-ioctl capabilities. These limitations are retained, not redesigned away.

## Contract and reduction review

The model covers read/write/clear/resize/capacity, including zero-length calls,
short transfers, EAGAIN, EINVAL and EMSGSIZE. Added tests deliberately violate
clear semantics, capacity reporting and invalid-resize rejection. SET_MODE is
not added to the model: the adapter always opens O_NONBLOCK, and testing global
mode/wakeup semantics requires blocking Linux workloads. Approximate counters
are not artificially treated as linearizable state.

The DFS remains bounded at 12 operations and configurable state budget; budget
exhaustion is INCONCLUSIVE. It enforces real-time and worker order. Executable
deletion replays from empty state and retains workers. The new recorded reducer
only removes suffixes at quiescent cuts: no excluded operation can overlap the
retained prefix. It does not manufacture a read failure by deleting an overlapping
producer. HISTORY_COUNTEREXAMPLE explicitly has executed=false.

No new high-severity kernel defect is asserted from source inspection alone.
Absence of such a finding is not a clean Linux validation result.
