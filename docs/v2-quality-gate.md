# V2 quality gate

Report date: 2026-10-29. Overall: **PARTIALLY COMPLETE**, not production-ready.
Latest follow-up: **83 tests passed**, including five mocked Linux-device
lifecycle tests. Evidence: artifacts/v2-device-lifecycle-20261029/tests.log and
result.json. These tests do not open a real device or validate kernel behavior.
The adapter now invalidates closed descriptors and preserves primary setup and
workload errors when cleanup also fails.
The preceding follow-up passed 78 tests, including preservation of measurement
errors when endpoint cleanup also fails. Evidence:
artifacts/v2-measurement-cleanup-20261029-verified/tests.log and result.json.
The initial sandbox run encountered temporary-file permission errors; its log
is retained in artifacts/v2-measurement-cleanup-20261029. The successful rerun
used approved access outside the sandbox. No new Linux validation was performed.
The user confirmed that no disposable Linux VM is available. No Linux provisioner
was found in PATH or the checked standard installation paths; WSL still reports
Installing. The kernel gates remain blocked, not waived.
The saved v2 verification run passed 75 Python tests after independently
reproducing the 64-test baseline. Shell syntax and checker regression passed.
The final 2026-10-27 run also passed all 75 tests and git diff --check. Browser
QA passed for the fault and control reports at widths 1440, 768, 390 and 320,
including filtering, evidence expansion, witness navigation, no horizontal
overflow and no browser errors. The 320-pixel failure screenshot was visually
inspected. Logs and command results are in artifacts/v2-final-20261027.
No existing work was reset, committed, pushed, or removed.

## Phase acceptance

| Phase | Status | Evidence / remaining gate |
| --- | --- | --- |
| 0 Audit | VERIFIED COMPLETE for the bounded review | v2-engineering-audit.md; reproducible harness fixes and regressions |
| 1 Linux execution | BLOCKED | v2-baseline WSL logs; Ubuntu Installing, WSL_E_DISTRO_NOT_FOUND; v2-linux manifest |
| 2 Contract | PARTIALLY COMPLETE | Five operations tested, additional invalid-control fixtures; blocking/SET_MODE excluded |
| 3 Reduction | PARTIALLY COMPLETE | Executable simulation and quiescent-prefix history reduction tested; real-device reduction unavailable |
| 4 Stress/replay | PARTIALLY COMPLETE | Seeds, workers, lengths, ratios, payload, capacity, jitter and repeats; nonblocking only, no deterministic scheduling |
| 5 Kernel fault lab | IMPLEMENTED BUT UNVERIFIED | C interrupted-write regression added; existing partial-copy/read/startup tests retained; kernel execution blocked |
| 6 Diagnostics | BLOCKED | No guest config or diagnostic execution; availability/enabled status unknown |
| 7 Performance | PARTIALLY COMPLETE | Windows pipe/socket samples with dispersion/CPU ratios; Linux baseline and native profiling blocked |
| 8 Research | VERIFIED COMPLETE for declared simulated study | 240 reductions, all outcomes retained, negative comparisons reported; no kernel/novelty claim |
| 9 Evidence pipeline | PARTIALLY COMPLETE | Fault/control demo reports and source snapshots; device path fails explicitly, no fallback; kernel correlation blocked |
| 10 Quality gate | PARTIALLY COMPLETE | Portable tests/shell checks passed; C build, integration and sanitizers unavailable |
| 11 Presentation | VERIFIED COMPLETE for current scope | README entry, v2 workflow, source-based interview defense and limitations |

FAILED is reserved for a demonstrated failing acceptance test. Device preflight
returns exit 2 and is labeled BLOCKED in its manifest; the generic command logger
records its nonzero exit as failed. Deliberately injected contract mismatches are
expected experiment observations, not passing device behavior.

## Diagnostics gate

| Tool | AVAILABLE | ENABLED | EXECUTED | Outcome |
| --- | --- | --- | --- | --- |
| KUnit | Unknown | Unknown | No | BLOCKED |
| KASAN | Unknown | Unknown | No | BLOCKED |
| KCSAN | Unknown | Unknown | No | BLOCKED |
| lockdep | Unknown | Unknown | No | BLOCKED |
| UBSAN | Unknown | Unknown | No | BLOCKED |
| kmemleak | Unknown | Unknown | No | BLOCKED |
| Allocation injection | Unknown | Unknown | No | BLOCKED |

In an authorized disposable guest first use linux-validation.md. Save the actual
kernel config and module identity. For each diagnostic kernel run the same
snapshot integration workflow into a new output directory; inspect executed
workload and logs, not merely CONFIG values. KUnit's `make kunit` is build-only:
execution additionally requires loading ringbuf_char_test.ko on its matching
configured guest and preserving KTAP/dmesg and cleanup. Use an external VM
watchdog; a Python timeout cannot recover a wedged kernel. Allocation injection
must follow the bounded task-filtered protocol in fault-injection.md. No host
kernel settings were changed.

## Evidence inventory

- artifacts/v2-baseline: independent baseline and WSL execution logs.
- artifacts/v2-verification: 75-test log, shell logs, demo/benchmark commands and exit codes.
- artifacts/v2-linux: blocked Linux validation manifest, no fabricated module.
- artifacts/v2-study: 240 raw reductions, summaries and exact source snapshot.
- artifacts/v2-demo-fault: three expected faulty runs, reduction, reports and provenance.
- artifacts/v2-demo-control: three nonblocking correct-fixture runs and reports.
- artifacts/v2-demo-device: explicit BLOCKED, no simulated run directories.
- artifacts/v2-windows-benchmark: six repeats, 6000 CSV samples and summaries.
- artifacts/v2-browser: offline report viewport screenshots when browser checks run.
- artifacts/v2-final-20261027: final regression, browser, whitespace and WSL logs.
- artifacts/v2-measurement-cleanup-20261029: sandbox-restricted test failure log.
- artifacts/v2-measurement-cleanup-20261029-verified: 78 passing portable tests.

These artifacts are local and Git-ignored. Regenerate using v2-workflow.md rather
than assuming a clone contains the evidence. Manifests identify the exact source
used; subsequent fixes do not retroactively change earlier snapshots.

## Remaining priorities

Provision an authorized disposable Linux guest and matching headers. Compile all
C changes, execute integration and KUnit, then diagnostic kernels and allocation
fault tests. Only after that gate should real-device reduction, blocking stress,
SET_MODE modeling, diagnostic correlation and Linux performance be called
validated. Keep device reduction and causality-aware research deferred until
there is evidence to evaluate them against.
