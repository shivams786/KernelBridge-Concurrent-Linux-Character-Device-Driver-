#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT="${ROOT_DIR}/userspace/shivam_char_client"
TMP_DIR="$(mktemp -d)"

cleanup() {
  if [[ -n "${WRITER_PID:-}" ]]; then
    wait "$WRITER_PID" 2>/dev/null || true
  fi
  bash "${ROOT_DIR}/scripts/unload.sh" --quiet || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

make -C "$ROOT_DIR" module userspace
bash "${ROOT_DIR}/scripts/reload.sh"

"$CLIENT" clear >/dev/null

if [[ "$("$CLIENT" poll-read 200)" != "timeout" ]]; then
  echo "FAIL: empty device was reported readable" >&2
  exit 1
fi

(sleep 0.2; "$CLIENT" write wake >/dev/null) &
WRITER_PID=$!

if [[ "$("$CLIENT" poll-read 5000)" != "readable" ]]; then
  echo "FAIL: poll did not wake for delayed writer" >&2
  exit 1
fi

wait "$WRITER_PID"
unset WRITER_PID

"$CLIENT" read 4 >"${TMP_DIR}/poll_read"
if ! grep -qx 'wake' "${TMP_DIR}/poll_read"; then
  echo "FAIL: poll wake data did not match" >&2
  exit 1
fi

if [[ "$("$CLIENT" poll-write 100)" != "writable" ]]; then
  echo "FAIL: non-full device was not reported writable" >&2
  exit 1
fi

echo "PASS: poll/select readiness behavior"

