#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STRICT=0
BUILD_MODULE=0

usage() {
  cat <<'USAGE'
Usage: bash scripts/dev_check.sh [--strict] [--module]

Runs repository-level checks that are safe for local development.

Options:
  --strict  fail when optional tools are missing
  --module  try to build the kernel module when headers are available
USAGE
}

log() {
  printf 'dev_check: %s\n' "$*"
}

pass() {
  printf 'PASS: %s\n' "$*"
}

skip() {
  printf 'SKIP: %s\n' "$*"
  if [[ "$STRICT" -eq 1 ]]; then
    printf 'dev_check: strict mode treats skipped checks as failures\n' >&2
    exit 1
  fi
}

for arg in "$@"; do
  case "$arg" in
    --strict)
      STRICT=1
      ;;
    --module)
      BUILD_MODULE=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'dev_check: unknown option: %s\n' "$arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

cd "$ROOT_DIR"

required_files=(
  README.md
  LICENSE
  Makefile
  Kbuild
  include/ringbuf_char_ioctl.h
  kernel/ringbuf_char.c
  kernel/ringbuf_char_buffer.c
  kernel/ringbuf_char_buffer.h
  userspace/client.c
  userspace/concurrent_test.c
  userspace/Makefile
  tests/run_all_tests.sh
  scripts/load.sh
  scripts/unload.sh
  scripts/inspect.sh
  docs/PROJECT_ASSESSMENT_AND_ROADMAP.md
  docs/system-design/HLD.md
  docs/system-design/LLD.md
  docs/system-design/database-design.md
  docs/api/API_SPECIFICATION.md
  docs/security/threat-model.md
  docs/TECHNICAL_DEBT.md
)

log "checking required files"
for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    printf 'dev_check: missing required file: %s\n' "$file" >&2
    exit 1
  fi
done
pass "required files exist"

log "checking shell syntax"
bash -n scripts/*.sh tests/*.sh
pass "shell syntax"

log "checking generated-placeholder phrases"
if grep -RInE --exclude=dev_check.sh \
  'same as above|implementation omitted|add your logic here|for brevity|TODO' \
  README.md docs include kernel userspace scripts tests; then
  printf 'dev_check: placeholder phrase found\n' >&2
  exit 1
fi
pass "no placeholder phrases found"

if command -v make >/dev/null 2>&1; then
  log "building user-space tools"
  make userspace
  pass "user-space build"
else
  skip "make not available; user-space build not run"
fi

if command -v shellcheck >/dev/null 2>&1; then
  log "running shellcheck"
  shellcheck scripts/*.sh tests/*.sh
  pass "shellcheck"
else
  skip "shellcheck not installed"
fi

if command -v cppcheck >/dev/null 2>&1; then
  log "running cppcheck"
  cppcheck --enable=warning,style,performance,portability \
    --error-exitcode=1 --std=c11 -Iinclude userspace
  pass "cppcheck"
else
  skip "cppcheck not installed"
fi

if [[ -d "/lib/modules/$(uname -r)/build" ]]; then
  pass "kernel headers found"
  if [[ "$BUILD_MODULE" -eq 1 ]]; then
    log "building kernel module"
    make module
    pass "kernel module build"
  else
    skip "kernel headers available, but module build not requested; pass --module to build it"
  fi
else
  skip "kernel headers not found at /lib/modules/$(uname -r)/build"
fi

log "developer checks completed"
