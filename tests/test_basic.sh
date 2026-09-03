#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT="${ROOT_DIR}/userspace/ringbuf_char_client"
DEVICE="/dev/ringbuf_char"
TMP_DIR="$(mktemp -d)"

cleanup() {
  bash "${ROOT_DIR}/scripts/unload.sh" --quiet || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

make -C "$ROOT_DIR" module userspace
bash "${ROOT_DIR}/scripts/reload.sh"

if [[ ! -c "$DEVICE" ]]; then
  echo "FAIL: ${DEVICE} is not a character device" >&2
  exit 1
fi

"$CLIENT" clear >/dev/null

MESSAGE="hello from ringbuf_char"
printf '%s' "$MESSAGE" >"${TMP_DIR}/expected"
"$CLIENT" write "$MESSAGE" >/dev/null
"$CLIENT" read "${#MESSAGE}" >"${TMP_DIR}/actual"

if ! cmp -s "${TMP_DIR}/expected" "${TMP_DIR}/actual"; then
  echo "FAIL: read data did not match written data" >&2
  printf 'expected: %s\n' "$MESSAGE" >&2
  printf 'actual:   ' >&2
  cat "${TMP_DIR}/actual" >&2
  printf '\n' >&2
  exit 1
fi

"$CLIENT" read 0 >"${TMP_DIR}/zero_read"
if [[ -s "${TMP_DIR}/zero_read" ]]; then
  echo "FAIL: zero-length read produced output" >&2
  exit 1
fi

"$CLIENT" write "" >/dev/null

exec 9<>"$DEVICE"
exec 9>&-

echo "PASS: basic open/write/read/zero-length behavior"

