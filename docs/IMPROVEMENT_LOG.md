# Improvement Log

## 2026-09-03 - Driver Rename to `ringbuf_char`

Problem: the original module name was personal. It worked, but it did not
describe the device behavior immediately.

Previous Implementation: module, device node, class, UAPI header, source files,
client binary, scripts, tests, and docs used a personal driver name.

New Implementation: renamed the driver to `ringbuf_char` across code, build
files, scripts, tests, and documentation.

Reason: `ringbuf_char` is still short, but it tells a reviewer the driver is a
character device backed by a ring/circular buffer.

Impact: demo commands now use `/dev/ringbuf_char`,
`ringbuf_char.ko`, and `userspace/ringbuf_char_client`.

Trade-Off: any old notes or commands using the previous name need to be updated
before the interview demo.

Files Changed:

- `include/ringbuf_char_ioctl.h`
- `kernel/ringbuf_char.c`
- `kernel/ringbuf_char_buffer.c`
- `kernel/ringbuf_char_buffer.h`
- `Kbuild`
- `userspace/Makefile`
- `scripts/*.sh`
- `tests/*.sh`
- `README.md`
- `docs/**/*.md`

## 2026-08-14 - System Design Package

Problem: the project had useful driver docs, but not a full architecture
package for interview or production-readiness discussion.

Previous Implementation: README plus focused docs for architecture, testing,
design decisions, and interview notes.

New Implementation: added assessment, HLD, LLD, API/ABI spec, state model,
capacity plan, tradeoffs, failure scenarios, caching strategy, scaling
strategy, observability notes, security threat model, security checklist,
operations runbook, ADRs, scorecard, and technical-debt log.

Reason: a systems portfolio project should show not only code, but also the
engineering judgment around deployment, failure handling, security, and future
evolution.

Impact: reviewers can understand what exists, what is intentionally absent,
and how the project can grow without adding unrelated infrastructure.

Trade-Off: more documentation to maintain when the ABI or scripts change.

Files Changed:

- `docs/PROJECT_ASSESSMENT_AND_ROADMAP.md`
- `docs/system-design/*`
- `docs/architecture/*`
- `docs/security/*`
- `docs/api/API_SPECIFICATION.md`
- `docs/operations/runbook.md`
- `docs/adr/*`
- `docs/TECHNICAL_DEBT.md`
- `docs/ARCHITECTURE_SCORECARD.md`

## 2026-08-14 - Developer Verification Script

Problem: local verification depended on remembering several commands and did
not explain skipped checks clearly.

Previous Implementation: `make`, `make userspace`, optional lint targets, and
VM integration tests.

New Implementation: `scripts/dev_check.sh` runs structure checks, shell syntax
checks, optional static tools, user-space build when `make` is available, and a
kernel-header check. `make verify` calls it.

Reason: contributors need one safe first command that does not pretend skipped
Linux-only checks passed.

Impact: easier onboarding and clearer local feedback.

Trade-Off: the script is another maintained surface.

Files Changed:

- `scripts/dev_check.sh`
- `Makefile`
- `.github/workflows/userspace-build.yml`

## 2026-08-14 - Editor Configuration

Problem: contributors could edit files with inconsistent line endings or
indentation, especially when moving between Windows and Linux VMs.

Previous Implementation: formatting expectations were implicit.

New Implementation: added `.editorconfig` with LF endings, final newlines, tab
indentation for C/Kbuild/Makefile files, and two-space indentation for docs,
YAML, and shell scripts.

Reason: small consistency rules prevent noisy diffs without forcing a heavy
formatting toolchain.

Impact: easier cross-platform editing and cleaner reviews.

Trade-Off: editors need EditorConfig support to apply it automatically.

Files Changed:

- `.editorconfig`
