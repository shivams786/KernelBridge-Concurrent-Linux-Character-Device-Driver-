#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODULE_NAME="ringbuf_char"
MODULE_PATH="${ROOT_DIR}/${MODULE_NAME}.ko"
DEVICE_PATH="/dev/${MODULE_NAME}"
CLIENT="${ROOT_DIR}/userspace/ringbuf_char_client"

section() {
  printf '\n== %s ==\n' "$1"
}

section "System"
uname -a
printf 'kernel release: %s\n' "$(uname -r)"

section "Module File"
if [[ -f "$MODULE_PATH" ]]; then
  modinfo "$MODULE_PATH" || true
else
  echo "module file not built: ${MODULE_PATH}"
fi

section "Loaded Module"
if lsmod | awk '{print $1}' | grep -qx "$MODULE_NAME"; then
  lsmod | awk -v module="$MODULE_NAME" '$1 == module { print }'
else
  echo "${MODULE_NAME} is not loaded"
fi

section "Device Node"
if [[ -e "$DEVICE_PATH" ]]; then
  if command -v stat >/dev/null 2>&1; then
    stat -c '%n permissions=%A owner=%U group=%G major_minor=%t:%T' \
      "$DEVICE_PATH"
  else
    ls -l "$DEVICE_PATH"
  fi
else
  echo "${DEVICE_PATH} is absent"
fi

section "Driver Statistics"
if [[ -x "$CLIENT" && -e "$DEVICE_PATH" ]]; then
  "$CLIENT" stats || true
else
  echo "statistics unavailable; build userspace client and load module first"
fi

section "Recent Logs"
dmesg 2>/dev/null | grep 'ringbuf_char:' | tail -50 || true

