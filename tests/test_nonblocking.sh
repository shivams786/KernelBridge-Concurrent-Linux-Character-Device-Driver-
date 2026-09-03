#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT="${ROOT_DIR}/userspace/ringbuf_char_client"
TMP_DIR="$(mktemp -d)"

cleanup() {
  bash "${ROOT_DIR}/scripts/unload.sh" --quiet || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

make -C "$ROOT_DIR" module userspace
bash "${ROOT_DIR}/scripts/reload.sh" buffer_capacity=256

"$CLIENT" clear >/dev/null

if "$CLIENT" --nonblock read 1 >"${TMP_DIR}/empty.out" 2>"${TMP_DIR}/empty.err"; then
  echo "FAIL: non-blocking read from empty buffer unexpectedly succeeded" >&2
  exit 1
fi
grep -Eqi 'Resource temporarily unavailable|EAGAIN' "${TMP_DIR}/empty.err"

"$CLIENT" fill X 256 >/dev/null

if "$CLIENT" --nonblock write Z >"${TMP_DIR}/full.out" 2>"${TMP_DIR}/full.err"; then
  echo "FAIL: non-blocking write to full buffer unexpectedly succeeded" >&2
  exit 1
fi
grep -Eqi 'Resource temporarily unavailable|EAGAIN' "${TMP_DIR}/full.err"

"$CLIENT" read 128 >/dev/null
"$CLIENT" --nonblock write Z >/dev/null

echo "PASS: non-blocking EAGAIN and recovery behavior"

