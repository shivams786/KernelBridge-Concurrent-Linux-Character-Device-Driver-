# Frozen Level 3 evaluation protocol

Written before the full evaluation; the initial 30-job smoke run tested the
pipeline. Smoke results are not used to select favorable full-study cases.
Configuration is in lab/research.py:CONFIGS and copied into every bundle.

Full: nine conditions (correct control plus eight faults), seeds 11 and 29,
workers 2 and 4, lengths 6 and 10, no dependencies or dense chain dependencies.
This is 144 paired workloads and five unique strategies, 720 jobs. Every job
has 120 actual search executions maximum, 100 candidate evaluations maximum,
five initial/final trials, and 20 separate holdout executions. The dependency
ablation uses one candidate trial; other methods use five. Job timeout is 45s.
Order is shuffled with seed 2026. Algorithm trial stream starts at 809;
workload generation uses a separate seed. Holdout starts at 1000809.

The strict and reproduction-aware methods differ in candidate acceptance, not
in information access, initial screening, final confirmation or holdout policy.
No invalid candidate is executed by any method. Dense dependencies are
synthetic inclusion constraints, not recovered kernel resource dependencies.
They intentionally make some removals impossible and can hurt DRADD.

Sensitivity: intermittent EOF, seeds 11/29/47, workers 2, length 8, none/dense
dependencies, thresholds 0.4 and 0.8, five methods = 60 jobs. Smoke additionally
exercises sparse constraints. All configurations terminate with finite budgets.

Success criterion for a proposed advantage: more confirmed strictly smaller
reproducers or lower actual execution cost on paired inputs without reduced
holdout reliability. Candidate count alone is not speedup. Report size only
among jointly confirmed pairs and explicitly retain unconfirmed runs. Record
wall time separately from replay time and operation counts. No claim of
statistical superiority from two workload seeds. Report medians, means,
percentiles and paired differences. Per-run Wilson intervals apply only under
the stated binomial model; repeated trials are not independent workloads.

Hypotheses to test, not assumptions: closure may reduce rejected candidates;
fixed replay may avoid accepting intermittent one-off symptoms but cost more;
chain constraints may prevent size reduction; a fault activated independently
of workload contents cannot become inherently more reliable by deleting noise.

No evaluation against native ddmin, ProbDD, syzkaller or Porcupine executables
is implied. These are related work, not measured competitors. The study is
Windows/Python controlled simulation, not Linux-driver performance testing.
