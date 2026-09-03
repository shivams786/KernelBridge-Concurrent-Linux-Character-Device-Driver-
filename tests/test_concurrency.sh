#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT="${ROOT_DIR}/userspace/ringbuf_char_client"
CONCURRENT="${ROOT_DIR}/userspace/concurrent_test"
TMP_DIR="$(mktemp -d)"

cleanup() {
  bash "${ROOT_DIR}/scripts/unload.sh" --quiet || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

make -C "$ROOT_DIR" module userspace
bash "${ROOT_DIR}/scripts/reload.sh" buffer_capacity=65536

"$CLIENT" clear >/dev/null
timeout 30 "$CONCURRENT" --writers 4 --readers 4 --messages 250 --size 64 \
  >"${TMP_DIR}/concurrency.out" 2>"${TMP_DIR}/concurrency.err"

grep -qx 'validation_failures: 0' "${TMP_DIR}/concurrency.out"
grep -qx 'missing_messages: 0' "${TMP_DIR}/concurrency.out"
grep -qx 'frames_validated: 1000' "${TMP_DIR}/concurrency.out"

if dmesg 2>/dev/null | tail -200 |
  grep -Eiq 'BUG|WARNING|Oops|panic|use-after-free|invalid opcode'; then
  echo "FAIL: suspicious kernel log entry found after concurrency test" >&2
  dmesg | tail -200 >&2
  exit 1
fi

cat "${TMP_DIR}/concurrency.out"
echo "PASS: concurrent readers/writers completed without validation failures"

