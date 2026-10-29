# Reduction study: 2026-10-25

Evidence: SIMULATION. Command:

```sh
python3 -m lab.experiment --output artifacts/reduction-study-20261025
```

The saved manifest records Windows/Python versions, dirty Git state, source
hashes, seeds and budgets. results.json contains all 40 rows and summaries;
individual run JSON files retain every candidate scenario and replay history.
The follow-up bundle `artifacts/reduction-study-snapshot-20261025/` additionally
contains the exact lab sources under `source/`, with matching manifest hashes.
Its 40 runs reproduced all final sizes and median candidate-check counts in the
table below. The displayed timings remain from the original run; they are not
silently replaced or pooled with the follow-up.
Artifacts are local generated evidence, not committed source. Re-run with a new
output directory. No kernel code runs in this experiment.

## Design

Four fixture classes (correct control, false EOF, reversed read, resize loss),
five seeded placements of the required operation chain among 12 operations,
two strategies: 40 reductions. Two workers; three fresh trials per candidate;
100 candidate-group budget; 10000 checker states per trial. Job order shuffled
with seed 42. Required stateful operations stay on worker 0; other operations
query capacity on worker 1. This makes defect triggering independent of worker
scheduling, without making the schedule itself deterministic.

Independent variables: deletion strategy, fault class, placement seed.
Dependent variables: final operation count, candidate groups, elapsed time,
replay success and outcome. Both strategies use the same acceptance oracle.
Hypothesis: chunk deletion reduces candidate checks. No hypothesis of algorithmic
novelty or superior final size is assumed.

## Observations

| Fixture | Final size, both strategies | Single checks median [range] | Chunk checks median [range] | Single/chunk median ms |
| --- | --- | --- | --- | --- |
| Correct control | 12, no reproducer | 0 [0,0] | 0 [0,0] | 1.58 / 1.84 |
| False EOF | 1 | 19 [16,22] | 7 [5,8] | 25.16 / 10.46 |
| Reversed read | 2 | 22 [16,32] | 13 [7,18] | 28.48 / 17.99 |
| Resize loss | 3 | 30 [22,34] | 19 [17,26] | 37.54 / 27.25 |

All 30 faulty-fixture reductions had three successful final reproductions;
all 10 correct-control runs reported REPRODUCTION_FAILED as expected. These
observed 3/3 rates are not estimates of rare kernel-race reliability. Chunk
deletion used fewer median candidate checks here, but produced **no smaller
final workloads**. Report the null size result, not just the favorable timings.

## Threats and next experiment

Only three injected defects, tiny histories, five placements, and one host.
Noise consists of harmless capacity queries. There is no realistic adversarial
interleaving corpus, multi-defect root-cause separation, memory-usage study, or
independent-host replication of the timing experiment. The follow-up was on the
same host and is a reproducibility check, not an independent sample. Median/range are
descriptive statistics, not confidence intervals or significance claims.
The Python simulator lock and interpreter affect schedules. The reference model
can itself be wrong. Failure signatures identify a contract class only.

Next: obtain Linux correctness evidence, then collect real device histories
under controlled workloads before evaluating kernel replay. Do not extrapolate
these results to syzkaller, Porcupine, production kernels, or hardware drivers.
