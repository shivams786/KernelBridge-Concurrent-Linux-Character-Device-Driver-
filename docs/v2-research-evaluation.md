# V2 reduction evaluation

Report date: 2026-10-27. Measurements were captured on 2026-10-25; exact UTC
timestamps, Python version, platform and source hashes are in artifacts/v2-study.
Evidence class: SIMULATION. No real kernel was exercised.

## Hypothesis and method

Narrow hypothesis: chunk deletion reduces candidate work compared with single
deletion as bounded workload length grows, without reducing final size further.
This is a comparison of established deletion techniques, not a novel algorithm.

Command: `python3 -m lab.experiment --matrix-v2 --output artifacts/v2-study`.
Use a new directory when repeating it. The saved source/lab tree permits running
the same implementation independently of later working-tree changes.

Design: 4 fixture classes (correct control, false EOF, reversed read, resize
loss), 3 lengths (4/8/12), 2 worker counts (2/4), 5 placement seeds (0..4), and
2 strategies: **240 reductions**, or 120 matched strategy pairs. Job order is
shuffled with seed 42. Each candidate has 3 fresh trials; maximum 100 candidate
groups and 10000 search transitions per trial. Initial/final confirmation are
extra groups. All candidate histories are retained, including rejected ones.

Required fault-triggering operations retain order on worker 0; capacity-query
noise is distributed over the other workers. This tests reproducible stateful
faults, not rare races. Timing is measured separately from candidate counts.

## Results

180 faulty-fixture reductions found executable simulated reproducers. All 60
correct controls returned REPRODUCTION_FAILED, as expected for a reducer asked
to find a failure in a correct fixture. No experiment returned INCONCLUSIVE.
Final sizes tied in all 120 matched pairs: false EOF 1, reversed read 2, resize
loss 3; correct controls remained unreduced.

Medians below pool the 30 faulty runs per length/strategy across worker counts,
fault classes and seeds. Per-cell results remain in results.json.

| Length | Strategy | Candidate groups | Candidate operations executed | Wall time ms |
| --- | --- | ---: | ---: | ---: |
| 4 | single | 6 | 33 | 12.688 |
| 4 | chunk | 7 | 45 | 11.897 |
| 8 | single | 13 | 144 | 27.272 |
| 8 | chunk | 9 | 72 | 16.938 |
| 12 | single | 22 | 348 | 42.388 |
| 12 | chunk | 13 | 108 | 25.000 |

Chunk deletion required more candidate groups in 28 of 120 pairs. It took
longer wall time in 39 pairs, including correct-control runs. Fewer groups do
not necessarily imply lower wall time: groups differ in length/search effort,
and the host scheduler introduces noise. The hypothesis is supported for the
pooled longer fixtures, not uniformly. There is **no final-size advantage**.

Raw rows include total trials, total operations, candidate-only operations,
search transitions, elapsed time, final size, matching-failure rate and outcome.
Counters are summed from captured trials, not estimated from the plan. The
matching rate is a contract-class rate, never proof of preserved root cause.

## Prior art and boundaries

[Delta debugging](https://www.st.cs.uni-saarland.de/dd/) establishes systematic
test-case simplification. Our adaptive complement deletion is a small bounded
implementation, not a claim to implement every ddmin variant or prove global
minimality. [syzkaller reproduction](https://github.com/google/syzkaller/blob/master/docs/reproducing_crashes.md)
already addresses kernel reproducers; KernelBridge complements it with a narrow
FIFO contract oracle. [Porcupine](https://github.com/anishathalye/porcupine) is an
established linearizability checker; our DFS is not a scalability competitor.
[KCSAN](https://www.kernel.org/doc/html/latest/dev-tools/kcsan.html) checks dynamic
data races, a different question from whether captured results admit a legal
FIFO ordering. None of these tools is replaced here.

Dependency-aware reduction is deferred: fresh execution already rejects lost
producer/control prerequisites, and this corpus does not justify a new causal
inference engine. The stretch goal requires real validation that is still
blocked. Temporal ordering is not labeled causality.

Threats: synthetic faults, harmless query noise, tiny histories, one machine,
Python scheduling/locking, shared written specification, no realistic lifecycle
dependency corpus, no confidence intervals or significance tests. Seed changes
vary placements, not independent host populations. No broad superiority claim.

## Performance is a separate experiment

artifacts/v2-windows-benchmark contains 6000 raw 64-byte round trips: two
transports, three repeats, 1000 samples/repeat after 100 warmups. Pipe median
logical throughput was 26.36 MiB/s (range 25.45..27.50); socketpair 11.01 MiB/s
(6.75..12.97). Median per-repeat p99 was 3.6 us and 19.2 us respectively.
These are Windows/Python end-to-end measurements, not Linux driver latency or
maximum throughput. Per-run mean, population standard deviation, CPU-time ratio,
and available resource counters are saved; Windows resource counters may be null.
No kernel optimization or native benchmark was justified without a Linux profile.
