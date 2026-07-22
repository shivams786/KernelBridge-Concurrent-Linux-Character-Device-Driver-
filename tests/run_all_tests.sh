#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/tests/logs/$(date +%Y%m%d-%H%M%S)"
TEST_TIMEOUT="${TEST_TIMEOUT:-45}"
TESTS=(
  test_basic.sh
  test_ioctl.sh
  test_nonblocking.sh
  test_poll.sh
  test_concurrency.sh
)
PASSED=0
FAILED=0

cleanup() {
  bash "${ROOT_DIR}/scripts/unload.sh" --quiet || true
}
trap cleanup EXIT

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run_all_tests: integration tests load a kernel module; rerun with sudo" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
echo "run_all_tests: logs will be written to ${LOG_DIR}"

BASE_DMESG_LINES="$(dmesg 2>/dev/null | wc -l || printf '0')"

make -C "$ROOT_DIR" all

run_one() {
  local test_name="$1"
  local log_file="${LOG_DIR}/${test_name%.sh}.log"

  printf 'RUN  %s\n' "$test_name"
  if timeout "$TEST_TIMEOUT" bash "${ROOT_DIR}/tests/${test_name}" \
    >"$log_file" 2>&1; then
    printf 'PASS %s\n' "$test_name"
    PASSED=$((PASSED + 1))
  else
    printf 'FAIL %s\n' "$test_name"
    FAILED=$((FAILED + 1))
    sed 's/^/  | /' "$log_file"
  fi
}

for test_name in "${TESTS[@]}"; do
  run_one "$test_name"
done

DMESG_LOG="${LOG_DIR}/dmesg_after_tests.log"
dmesg 2>/dev/null | tail -n +"$((BASE_DMESG_LINES + 1))" >"$DMESG_LOG" || true

if grep -Eiq 'BUG|WARNING|Oops|panic|use-after-free|invalid opcode' \
  "$DMESG_LOG"; then
  echo "FAIL dmesg scan found a suspicious kernel entry"
  sed 's/^/  | /' "$DMESG_LOG"
  FAILED=$((FAILED + 1))
fi

printf '\nSummary: %d passed, %d failed\n' "$PASSED" "$FAILED"
printf 'Logs: %s\n' "$LOG_DIR"

if [[ "$FAILED" -ne 0 ]]; then
  exit 1
fi

echo "All integration tests passed"
