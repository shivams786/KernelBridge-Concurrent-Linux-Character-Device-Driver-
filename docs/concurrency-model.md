# Concurrent checking and replay

## Observation model

`lab/concurrency.py` starts 2..4 workers through a barrier and records call
invocation/response times with perf_counter_ns. Device calls are not serialized
by the recorder. The simulator itself has a lock. At most 12 calls are checked.
By default calls are distributed round-robin; optional `worker_ids` assigns
each operation to a worker. Order within each worker is retained, including
after reduction. A reduced workload may leave a worker idle.
The runner accepts 1..12 operations with 2..4 workers, validates assignments
before creating a bundle, and refuses to discard worker_ids in sequential mode.
Replay a reduced scenario with the original worker count and fixture fault:

```sh
python3 -m lab.runner --scenario artifacts/replay/reduced.json --workers 2 --fault reverse-read --output artifacts/reduced-run
python3 -m lab.history artifacts/reduced-run
python3 -m lab.report artifacts/reduced-run
```

A reproduced failure returns exit code 1 from runner/history; that is expected
for a deliberately faulty simulator, not a successful-driver verdict.

`lab/history.py` searches sequential model executions respecting both per-worker
order and strict response-before-invocation precedence. Equal timestamps are
conservatively treated as overlapping. Search is capped at 100000 candidate
states (default 10000). PASS has a witness order; FAIL means exhaustive search
found no legal ordering; budget exhaustion or incomplete execution is
INCONCLUSIVE. The checker is cross-checked against a small permutation oracle,
which still shares the reference model and is not an independent specification.

Offline rechecking also validates the captured worker count, operation ownership,
and sequence against the saved scenario (round-robin or explicit worker_ids).
Malformed events and inconsistent metadata are rejected as CLI errors. Only
search-budget exhaustion may be reconsidered with a larger budget; an unknown
inconclusive execution reason stays inconclusive. These checks detect inconsistent
bundles, not coordinated tampering with every file or cryptographic authenticity.

Mutations in the driver are serialized under its mutex. For accessible-memory
read/write, the final FIFO update in that critical section is a suitable
abstract linearization point. Resize linearizes when replacement state is
installed; clear when state is emptied. A successful read cannot mutate the
buffer simultaneously with resize, although syscall intervals may overlap.

## Reduction experiment

`lab/replay.py` is explicitly simulation-only at the CLI. Every candidate is a
new workload executed against a fresh empty device, not a filtered old trace.
Deleting a write does not let its previously observed read result survive.
Worker ownership is retained, sequence numbers regenerated, timestamps
remeasured, and every fresh history checked. Candidate acceptance requires all
replay trials to fail with `NO_LEGAL_FIFO_ORDERING`; final confirmation is fresh.

Two ordinary baselines are provided: `single` deletes one operation at a time;
`chunk` uses adaptive chunk deletion. Neither is a novel failure-aware algorithm.
Both preserve dependencies through actual execution, not an inferred dependency
graph. The contract-failure class is NOT a root-cause signature: two unrelated
FIFO violations can satisfy it. No globally minimal reproducer is promised.

| Term | Meaning here |
| --- | --- |
| HISTORY_REDUCED | A smaller recorded counterexample only; not emitted by this executable reducer |
| EXECUTABLE_REPRODUCER_FOUND | Final fresh trials all reproduced the contract-failure class |
| REPRODUCTION_FAILED | Required initial/final trials did not all reproduce; not proof the original bug vanished |
| INCONCLUSIVE | Required replay had errors or exhausted checker budget |
| CONTROLLED_START | Common barrier, not controlled scheduling inside calls |
| REPEATED_SCHEDULE_ATTEMPT | Multiple independent executions |
| OBSERVED_REPRODUCTION | Observed failure class in fresh execution; boolean in saved result |
| DETERMINISTIC_REPLAY | Not implemented or claimed |

The maximum candidate budget is 100 groups, with 1..20 trials per group.
Initial and final confirmation are extra, explicitly recorded groups. All
histories, candidates, counts, timing, and outcomes are retained in JSON.
The simulator has finite operations; arbitrary custom backends can still hang
inside Python threads. Use an external timeout, and do not treat this API as a
watchdog for kernel deadlocks. Kernel replay remains blocked on Linux validation.

## Reproduce

```sh
python3 -m lab.experiment --output artifacts/reduction-study
python3 -m lab.runner --backend simulated --workers 3 --steps 12 --output artifacts/concurrent-demo
python3 -m lab.history artifacts/concurrent-demo --budget 100000
python3 -m lab.report artifacts/concurrent-demo
```

Study results contain `input` and `reduced` scenarios. To reduce a standalone
scenario file (with optional worker_ids), use:

```sh
timeout 120s python3 -m lab.replay --scenario scenario.json --fault reverse-read --workers 2 --strategy chunk --trials 3 --output artifacts/replay
```

The existing HTML report consumes runner bundles, not study/replay JSON. Those
formats remain separate to avoid displaying an execution-reproduction verdict
as a generic driver pass. The study command requires no device or privilege.

## Saved source

New study and replay bundles retain `source/lab/*.py` as well as the per-file
SHA-256 values in manifest.json. This uses the same path-checked snapshot helper
as Linux validation; Python source bytes are not normalized. Older bundles
containing only hashes are not retroactively claimed to contain source.

To rerun the full study from the captured implementation:

```sh
cd artifacts/reduction-study-snapshot-20261025/source
python3 -m lab.experiment --output ../repeat-from-source
```

Use a new output directory. The source snapshot is not a Python/runtime/OS image,
and does not make thread scheduling deterministic. Keep the original manifest
for capture provenance: Git metadata queried during a later rerun describes
that rerun's environment. Do not edit lab sources during capture. Tests verify
snapshot hashes and run a reduced fixture in a subprocess from the saved source.
