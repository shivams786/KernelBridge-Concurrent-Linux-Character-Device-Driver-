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
bash "${ROOT_DIR}/scripts/reload.sh"

"$CLIENT" clear >/dev/null

CAPACITY="$("$CLIENT" capacity)"
if [[ "$CAPACITY" != "4096" ]]; then
  echo "FAIL: expected default capacity 4096, got ${CAPACITY}" >&2
  exit 1
fi

RESIZED="$("$CLIENT" resize 8192)"
if [[ "$RESIZED" != "8192" ]]; then
  echo "FAIL: resize output was ${RESIZED}" >&2
  exit 1
fi

if [[ "$("$CLIENT" capacity)" != "8192" ]]; then
  echo "FAIL: capacity did not change to 8192" >&2
  exit 1
fi

"$CLIENT" stats >"${TMP_DIR}/stats"
grep -qx 'abi_version: 1' "${TMP_DIR}/stats"
grep -qx 'capacity: 8192' "${TMP_DIR}/stats"
grep -qx 'stored_bytes: 0' "${TMP_DIR}/stats"

"$CLIENT" reset-stats >/dev/null
"$CLIENT" stats >"${TMP_DIR}/stats_after_reset"
grep -qx 'total_bytes_read: 0' "${TMP_DIR}/stats_after_reset"
grep -qx 'total_bytes_written: 0' "${TMP_DIR}/stats_after_reset"

"$CLIENT" fill A 300 >/dev/null
if "$CLIENT" resize 256 >"${TMP_DIR}/resize_small.out" 2>"${TMP_DIR}/resize_small.err"; then
  echo "FAIL: resize smaller than unread data unexpectedly succeeded" >&2
  exit 1
fi
grep -Eqi 'Message too long|Invalid argument' "${TMP_DIR}/resize_small.err"

"$CLIENT" clear >/dev/null
if "$CLIENT" resize 128 >"${TMP_DIR}/resize_invalid.out" 2>"${TMP_DIR}/resize_invalid.err"; then
  echo "FAIL: invalid resize unexpectedly succeeded" >&2
  exit 1
fi
grep -Eqi 'Invalid argument|Numerical result out of range' \
  "${TMP_DIR}/resize_invalid.err"

if "$CLIENT" invalid-ioctl >"${TMP_DIR}/invalid_ioctl.out" 2>"${TMP_DIR}/invalid_ioctl.err"; then
  echo "FAIL: unsupported ioctl unexpectedly succeeded" >&2
  exit 1
fi
grep -Eqi 'Inappropriate ioctl|ENOTTY|ioctl' "${TMP_DIR}/invalid_ioctl.err"

echo "PASS: ioctl capacity/stats/clear/error paths"

