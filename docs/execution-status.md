# Full-roadmap acceptance ledger

This is the earlier roadmap ledger. For the latest 2026-10-27 v2 assessment,
75-test verification and 240-run study, see [v2-quality-gate.md](v2-quality-gate.md)
and [v2-final-report.md](v2-final-report.md). Historical evidence below is retained.

2026-10-25. Repository: linux-char-driver; branch main; base commit 152dacd.
The dirty tree includes earlier work and this iteration. No reset, commit, push,
or WSL installation change was performed. This is not a full-project completion
claim: critical Linux acceptance gates remain blocked.

| Phase | Acceptance criterion | Status and evidence |
| --- | --- | --- |
| 0: reconnaissance | Inventory architecture, preserve changes, run portable baseline | TESTED: 45 baseline tests passed; kernel/userspace/lab/scripts/CI inspected |
| 1: Linux validation | Matching-kernel build, suite, module identity, cleanup, diagnostics | BLOCKED: Ubuntu Installing; uname returns WSL_E_DISTRO_NOT_FOUND. Snapshot runner exists; no substitute runtime result |
| 2: correctness audit | Review lifetime/locking/UAPI/error paths; regress concrete fixes | Portable recheck cleanup bug fixed and tested. Driver logging bounded; ABI and signal regressions implemented, Linux verification blocked |
| 3: contract | State exact semantics and modeled subset; reject false evidence | IMPLEMENTED and portable model tests pass; device-contract.md separates runtime-only behavior |
| 4: concurrency | Fresh-execution reduction, preserved workers, repeated confirmation, uncertainty | TESTED in simulation: two deletion strategies, explicit outcomes, every candidate retained; kernel replay blocked |
| 5: fault injection | Selected bounded failures with cleanup and diagnostics | Simulator error/cleanup paths TESTED; C partial-copy, thread-start, signal tests implemented; kernel injections/diagnostics BLOCKED |
| 6: performance | Linux device baseline, profile before optimization | BLOCKED; existing harness preserved, no speculative optimization or Linux performance claim |
| 7: research evaluation | Fair baseline comparison, all outcomes and limits reported | EXPERIMENTAL: 40 simulated reductions, equal final sizes; candidate checks and raw histories retained; Linux study blocked |
| 8: portfolio | Accurate README, architecture, reproducible workflow, limitations/interview defense | IMPLEMENTED; documents link measured results and unfinished acceptance gates |

## What changed in this iteration

- Prevent offline rechecking from hiding execution/cleanup errors or missing
  results. Budget-limited histories still support larger-budget rechecking.
- Preserve explicit worker ownership through concurrent workload deletion;
  support idle workers and fresh per-trial histories.
- Add simulation-only repeated replay, single/chunk reduction, and a fixed
  comparative experiment, with regression coverage and source provenance.
- Bound success-path control logging; add v1 ABI compile assertions and an
  interrupted-blocking-read Linux regression. These C changes are not compiled
  or runtime-verified on this host.
- Add the source-based audit, exact contract, research/fault/performance notes,
  measured study, limitations, interview defense, and README demo entry point.

## Evidence locations

- `artifacts/reduction-study-20261025/`: original 40-run experiment; source hashes
  identify the lab bytes used before subsequent small validation/provenance edits.
- `artifacts/roadmap-verification-20261025/`: final portable and shell-check logs,
  WSL command output, and structured command results.
- `artifacts/linux-preflight-20261025/`: platform-blocked validation manifest.
- `artifacts/concurrent-demo-20261025/report.html`: fresh 12-operation simulation
  report; desktop/mobile screenshots are in the verification directory.

Final verification: **55 Python tests passed** (baseline: 45); shell syntax and
the shell-checker regression passed; `git diff --check` passed (only Git's
LF/CRLF configuration warnings). Browser checks passed at widths 1440, 768, 390,
and 320 for filters, witness navigation, no horizontal overflow, and no page
errors. An initial ad hoc browser assertion raced asynchronous hash navigation;
waiting for the opened detail, as the existing browser test does, resolved it
without changing the report. An initial sandboxed temporary-file test was
blocked by access permissions; the final full run used approved test access.

Generated artifacts are ignored by Git. They are evidence on the local machine,
not guaranteed available to someone cloning the repository; all regeneration
commands are documented. The experiment manifest is the authority for its input
source bytes, not an assumption that it matches every later edit.

## Remaining release gate

Latest replay handoff verification: **64 tests passed**. The runner now accepts
reduced workloads with idle workers, rejects malformed worker plans before
creating output, and refuses to silently ignore an explicit plan in sequential
mode. Three regressions reproduced those problems before the fix; the shared
runner/executor preflight resolves them. Evidence:
`artifacts/replay-handoff-verification-20261025/portable-tests.log` and
`result.json`. Linux runtime acceptance remains blocked.

Latest portable verification: **61 tests passed**, including executing a reduced
fixture from its saved Python sources in a separate process. Study/replay bundles
now preserve source bytes, not just hashes. The path-checked snapshot helper is
reused; no new dependency was added. Evidence is in
`artifacts/source-snapshot-verification-20261025/` and
`artifacts/reduction-study-snapshot-20261025/`. The additional 40-run study
reproduced the original reduced sizes and candidate-check medians; original
results remain untouched. This does not change any blocked Linux gate.

Follow-up on 2026-10-25: strengthened offline capture validation to check worker
ownership/program order against the saved workload, reject malformed events,
and retain unknown inconclusive results. Four regression tests first reproduced
the defects; after the fix the full **59-test portable suite passed**. Evidence:
`artifacts/capture-validation-20261025/portable-tests.log` and `result.json`.
The prior 55-test run remains preserved above. WSL was rechecked and still lists
Ubuntu as Installing. No kernel acceptance gate changed status.

Provision an authorized disposable Linux guest with matching build headers and
run the recorded snapshot workflow. Then run diagnostic-kernel/KUnit and bounded
fault experiments, collect a Linux performance baseline, and inspect all failed
or inconclusive evidence before making readiness claims. The implementation
work cannot replace these external execution requirements.
