# Level 3 repository audit

Audit date: 2026-10-29. Baseline: 83 portable tests passed in 13.25 seconds,
exit 0, artifacts/level3-baseline/tests.log and result.json. This replaces the
prompt's older 64-test count. No AGENTS.md was found in the workspace scan.
Git main has extensive existing tracked and untracked changes; none was reset,
committed or pushed. See the saved study manifests for exact Git status/revision.

## Inspected baseline

| Component / source | Observed capability | Remaining limitation |
| --- | --- | --- |
| kernel/ringbuf_char.c, ringbuf_char_buffer.h | Mutex-protected shared FIFO, interruptible waits, generation wakeups, partial user-copy accounting, ioctl, poll | Source review only; no build or runtime evidence here |
| include/ringbuf_char_ioctl.h | Version 1, fixed-width structures, capacity 256..65536, mode flags | No compat_ioctl implementation; do not claim 32-bit compatibility |
| userspace/abi_dump.c, regression_test.c, concurrent_test.c | ABI assertions, interrupted read/write, partial-copy, thread startup tests | Linux C compilation/execution blocked |
| lab/contract.py | Five nonblocking FIFO operations and independent reference state | No SET_MODE, blocking completion, open/close operation language |
| lab/concurrency.py:evaluate_concurrent | Threaded capture, worker order, error evidence, start barrier | ThreadPoolExecutor cannot stop an indefinitely blocked call |
| lab/history.py:check_history | Real-time/per-worker precedence; bounded DFS; explicit search exhaustion | At most 12 operations; equal timestamps conservatively overlap |
| lab/replay.py:reduce_concurrent | Single/chunk deletion, repeated matching symptoms, fresh executions | No dependency representation or confidence intervals; candidate-group budget excludes initial/final trials |
| lab/research* / lab/dradd.py | Absent before this mission | New implementation required; no previous DRADD evidence assumed |
| lab/validate_linux.py | Source snapshots, bounded child execution, module identity and log correlation | Kernel hangs require an external VM watchdog |
| lab/benchmark.py | Partial transfers, payload checking, dispersion and raw samples | Python round trips, not saturation throughput or Linux measurements |
| lab/report.py | Escaping, CSP, offline evidence presentation | Existing schema concerns v2 runs, not comparative studies |
| .github/workflows/*.yml | Userspace/static checks and two Ubuntu kernel-header builds | Configuration exists; no CI run claimed |
| artifacts/v2-study | 240 simulated reductions preserved | Not DRADD, not kernel faults, not evidence of novelty |

## Findings and disposition

1. Existing chunk and single algorithms must remain available. Level 3 adds a
   new engine; it does not rename old results as DRADD.
2. Existing FIFO operations have no explicit descriptor-producing operations.
   Descriptor lifetime belongs to LinuxDevice's context manager. A dependency
   graph must not invent open/read edges for operations the language lacks.
3. Reads may obtain bytes from several writes and overlapping orderings. No
   guessed read-to-write edge can support a causal claim. Declared inclusion
   constraints are distinct from happens-before constraints.
4. A failed linearizability check identifies a contract symptom, not a unique
   bug. The Level 3 signature deliberately names that symptom.
5. Candidate group counts obscure unequal replay effort. Level 3 budgets and
   reports actual executions, including initial and final confirmations.
6. Hashes alone do not validate statistical summaries. The new verifier checks
   source projection, dependency validity, trial accounting and final evidence.
7. Current WSL list still says Ubuntu Installing (artifacts/level3-environment).
   The user has confirmed no disposable VM. No host installation was modified.

No speculative kernel defect was patched. Previous lifecycle fixes remain in
lab/backends.py and lab/benchmark.py, with their original regression tests.

## Scope choices

The new engine has a small adapter interface, not a second FIFO checker. The
existing checker remains the oracle. Repeated sampling is fixed, not adaptive;
checkpoint files preserve progress, but mid-search resume is not claimed.
The second adapter is a sequential register fixture, not a second driver.
Wraparound and partial-copy defects are not meaningfully modeled by the deque
fixture, so those remain Linux regression/diagnostic work, not invented faults.
