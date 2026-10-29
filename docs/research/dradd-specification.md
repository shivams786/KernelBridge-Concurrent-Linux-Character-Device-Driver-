# DRADD specification

Dependency-Guided, Reproduction-Aware Delta Debugging is an experimental
integration, not a claimed new class of minimization algorithms.

## Problem

W = (O, P, D, C). O is a finite ordered list of operations with stable original
indexes. P assigns operations to workers and preserves each worker's subsequence.
D contains declared inclusion prerequisites; C contains initial state, adapter,
worker count, budgets, seeds and replay policy. An edge (a requires b) means that
retaining a requires retaining b. It does not establish observed causality or
force a cross-worker happens-before ordering. An adapter requiring cross-worker
execution dependencies must enforce them itself; the FIFO adapter does not.

Kinds are HARD_STRUCTURAL and CONTRACT_REQUIRED (enforced),
CONSERVATIVE_INFERRED and OPTIONAL_HEURISTIC (annotated, not enforced). Required
edge cycles and conflicts with worker program order are rejected. The original
workload is deep-copied and never modified. Reduced artifacts remap edges while
retaining original_ids. No worker is reassigned; idle workers are allowed.

S(W,e) is an adapter-defined observable symptom on a valid completed execution.
For FIFO it is FIFO:NO_LEGAL_ORDER, emitted only after exhaustive bounded search
finds no legal ordering. Search exhaustion is incomplete, not a failure.
Register uses REGISTER:STALE_AFTER_DELETE. Neither signature identifies a root
cause. A different signature is a completed non-target failure.

Observed frequency is k/n, where k is target matches and n is valid completed
attempts (target, pass or different failure). Timeouts, incomplete captures and
environment errors are separately counted. If n=0 the frequency is null.
The unknown true probability is not identified by this estimate.

Find a nonempty dependency-valid projection W' preserving P and C, with fewer
operations and/or lower execution cost, that meets a declared empirical replay
policy. A confirmed unchanged workload is reported as a reproducer with
strictly_reduced=false; it is not evidence of minimization success.

## Sampling and uncertainty

Default: five fresh attempts per group, all five must be valid, at least one
must match, and the point estimate must be at least 0.6. Report two-sided Wilson
95% intervals with z=1.959963984540054. Optional lower_bound additionally requires
the lower endpoint to exceed that value for reproduction-aware strategies.
Point-estimate and lower-bound policies are not interchangeable. At 5/5 the
lower endpoint is only about 0.566; this is not proof of reliable reproduction.

No adaptive sample count, early stopping or hypothesis-test significance claim.
Twenty holdout attempts use a separate fixed seed range and never affect search.
They mitigate selection bias, not all dependence. Shared fixtures and host
scheduling violate ideal independent identically distributed trial assumptions;
intervals are descriptive under a binomial model. Do not pool correlated trials
across workloads into one confidence interval.

## Algorithm

```text
validate workload, adapter, prerequisite/program-order graph, budgets
run fixed initial replay group; return classified failure if rejected
current := all original indexes; granularity := 2
while current has more than one operation and search budget remains:
    generate contiguous deletion chunks (or single deletions)
    for each deletion:
        if guided: iteratively delete dependents of absent prerequisites
        reject empty, structurally invalid or adapter-invalid candidates
        reserve final confirmation trials before spending candidate budget
        execute fixed trial group with fresh target instances
        accept only if policy passes; restart from smaller current
    if no accepted deletion: refine chunks, or stop at singletons
run a fresh reserved final group, even after search budget exhaustion
return workload, confirmed flag, search state, all trials and accounting
```

Every acceptance strictly reduces cardinality. Dependency pruning is a decreasing
fixed point over at most 12 indexes. Chunk refinement terminates at singleton
granularity. Candidate and actual-execution budgets are finite. Termination of
the algorithm assumes target calls terminate; study jobs have a 45-second
process watchdog. No userspace mechanism promises recovery from a wedged kernel.

## Baselines and fairness

| Method | Deletion | Candidate sampling | Prerequisite guidance |
| --- | --- | --- | --- |
| A single | Individual | Five, all match | Validate only |
| B chunk | Complement chunks, refine | Five, all match | Validate only |
| C legacy | Alias of B's candidate policy | Same as B in Level 3 | Same as B |
| D dependency | Chunks | One match | Prune dependents |
| E reproduction | Chunks | Five, point threshold | Validate only |
| DRADD | Chunks | Five, point threshold | Prune dependents |

B is complement chunk deletion, not a complete reimplementation of classic
ddmin's subset-and-complement search. The historical lab.replay CLI keeps its
own all-match initial/final policy. Level 3 uses common five-trial initial/final
thresholds for all methods, so C is not an independently measured baseline.
All methods receive the same dependency information and reject invalid inputs
before execution. DRADD cannot claim exclusive access to validity checking.
D intentionally ablates repeated candidate sampling; actual-execution budgets
and independent holdout counts are equal, candidate counts need not be.

## States and distinctions

SUCCESS_REPRODUCER requires final fresh matching evidence. Search state may
separately be SEARCH_BUDGET_EXHAUSTED. INVALID_CANDIDATE is never executed.
DIFFERENT_FAILURE, INCOMPLETE_EXECUTION, ENVIRONMENT_ERROR and
TARGET_FAILURE_NOT_REPRODUCED explain rejection. INCONCLUSIVE is reserved for
unclassifiable evidence. HISTORY_ONLY_REDUCTION belongs to the existing saved
history-prefix tool, not to executable search.

No monotonicity assumption: failure can disappear and reappear as operations
are removed. No global minimality or general 1-minimality guarantee with
nondeterminism, dependency closure, or exhausted budgets. Historical
counterexample trimming, executable replay, frequency estimation, deterministic
schedule replay and causal debugging are separate tasks; only the first three
are implemented, and history trimming remains the existing v2 tool.
