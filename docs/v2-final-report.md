# KernelBridge v2 final execution report

Report date: 2026-10-29. Overall status: PARTIALLY COMPLETE.
Latest follow-up: 83 portable tests pass, including five mocked device-adapter
lifecycle regressions. Closed descriptors are invalidated, repeated cleanup is
harmless, and setup/workload errors survive cleanup failures. Evidence:
artifacts/v2-device-lifecycle-20261029. No real Linux syscalls were validated.

Previous follow-up: 78 tests passed after extending benchmark cleanup to retain the
primary measurement error as well as setup errors while attempting every close.
The new regression reproduced the failure before the fix. The initial full run
hit sandbox temporary-file permission errors; an approved rerun passed.
Latest logs: artifacts/v2-measurement-cleanup-20261029-verified. Earlier evidence
and the restricted-run log remain preserved. No new Linux checks ran. The user
confirmed no disposable Linux VM is available; kernel validation remains blocked.

## 1. Executive assessment

The portable correctness/reproduction pipeline is stronger and has executed
evidence. Real Linux validation remains the highest-priority unresolved gate.
No production-readiness, salary, employment or novelty claim is made.

## 2. Implementation

Changed lab/replay.py for matched-signature rates and execution/search metrics;
lab/history.py for conservative recorded-history reduction; lab/concurrency.py
for error capture and seeded scheduling perturbations; lab/experiment.py for the
240-run matrix; lab/benchmark.py for dispersion/CPU ratios; lab/report.py for
replay and recorded-evidence sections. Added lab/demo.py, tests/test_v2.py and
tests/v2_report_browser.cjs. Extended userspace/regression_test.c with interrupted
write coverage. Updated README/architecture and added the v2 audit, workflow,
research, quality-gate and interview documents.

## 3. Correctness findings

Fixed a misleading reproduction rate that counted nonmatching failures, escaped
ordinary worker exceptions, and malformed backend results that bypassed the
inconclusive path. Focused regressions pass. History trimming retains possible
overlapping producers; executable reduction always re-observes fresh workloads.
See v2-engineering-audit.md for source locations and remaining kernel risks.

## 4. Linux validation

No module was compiled, loaded or executed on Linux. WSL Ubuntu is still
Installing, with prior execution returning WSL_E_DISTRO_NOT_FOUND. Rechecked on
2026-10-27. Device demo reports BLOCKED without simulation fallback. KUnit,
KASAN, KCSAN, lockdep, UBSAN, kmemleak, allocation injection and C regressions
remain unexecuted. A command logger's nonzero exit does not override the
validation manifest's explicit BLOCKED status.

## 5. Concurrency research

Implemented single/chunk executable deletion with repeated confirmation and
quiescent-prefix recorded-history trimming. The 240-run matrix covers four
fixture classes, three lengths, two worker counts and five seeds. There were
180 confirmed faulty-fixture reproducers and 60 expected correct-control
non-reproductions. Final sizes tied in all 120 strategy pairs. Chunk needed more
checks in 28 pairs and was slower in 39, including control pairs. No uniform
superiority or deterministic replay claim is supported.

## 6. Performance

Measured 6000 Windows/Python pipe/socketpair round trips at 64 bytes. Median
logical throughput: pipe 26.36 MiB/s, socketpair 11.01 MiB/s. Raw samples,
per-repeat percentiles, mean, population deviation and CPU-time ratios are saved.
These are not Linux-device measurements. No kernel optimization or native C
benchmark was added without a measurable Linux bottleneck.

## 7. Contribution

The useful integration is explicit FIFO contracts, bounded checking, executable
reduction, conservative recorded evidence, source snapshots and honest status
reporting for one small driver. Delta debugging, syzkaller, Porcupine, KUnit and
KCSAN already address related problems. Dependency-aware causality research is
deferred pending valid Linux evidence and a suitable evaluation corpus.

## 8. Verification matrix

All phases are assessed in v2-quality-gate.md. Portable baseline: 64 tests;
final: 75 tests passed. Shell checks passed. Two offline reports passed browser
checks at four widths; git diff --check passed. Contract/stress/reduction are
partial relative to the full requested scope: SET_MODE/blocking generation,
real-device reduction and automatic diagnostic correlation are not implemented.
Linux execution, diagnostics and device performance remain BLOCKED.

## 9. Evidence inventory

artifacts/v2-baseline; artifacts/v2-verification; artifacts/v2-final-20261027;
artifacts/v2-study; artifacts/v2-demo-fault; artifacts/v2-demo-control;
artifacts/v2-demo-device; artifacts/v2-linux; artifacts/v2-windows-benchmark;
artifacts/v2-browser. Each applicable bundle contains commands, outcomes,
histories, source identity or raw measurements. Source snapshots identify the
captured revision, not all subsequent edits. Artifacts are local/Git-ignored.
Use v2-workflow.md to regenerate into new directories.

## 10. Remaining priorities

Provision an authorized disposable Linux guest with matching headers. Build and
run the C/integration tests, verify cleanup and kernel logs, then diagnostic
kernels and allocation failures. Establish Linux performance before optimization.
Only then validate real-device reduction, blocking stress, control-state modeling
and diagnostic correlation. Existing changes were preserved; no commits, pushes,
resets, module insertion on the host or WSL installation changes were made.
