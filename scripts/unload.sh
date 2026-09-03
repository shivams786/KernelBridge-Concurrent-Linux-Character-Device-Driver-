#!/usr/bin/env bash
set -euo pipefail

MODULE_NAME="ringbuf_char"
DEVICE_PATH="/dev/${MODULE_NAME}"
QUIET=0

for arg in "$@"; do
  case "$arg" in
    --quiet)
      QUIET=1
      ;;
    --help|-h)
      echo "Usage: sudo bash scripts/unload.sh [--quiet]"
      exit 0
      ;;
    *)
      printf 'unload: unknown option: %s\n' "$arg" >&2
      exit 1
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "unload: unloading kernel modules requires root; rerun with sudo" >&2
  exit 1
fi

if [[ -e "$DEVICE_PATH" ]] && command -v fuser >/dev/null 2>&1; then
  HOLDERS="$(fuser "$DEVICE_PATH" 2>/dev/null || true)"
  if [[ -n "$HOLDERS" ]]; then
    echo "unload: processes are holding ${DEVICE_PATH}:" >&2
    fuser -v "$DEVICE_PATH" >&2 || true
  fi
fi

if ! lsmod | awk '{print $1}' | grep -qx "$MODULE_NAME"; then
  if [[ "$QUIET" -eq 0 ]]; then
    echo "unload: ${MODULE_NAME} is not loaded"
  fi
  exit 0
fi

if ! rmmod "$MODULE_NAME"; then
  cat >&2 <<EOF
unload: rmmod failed. The module may be busy.
unload: inspect holders with:
unload:   sudo fuser -v ${DEVICE_PATH}
EOF
  exit 1
fi

for _ in $(seq 1 50); do
  if [[ ! -e "$DEVICE_PATH" ]]; then
    break
  fi
  sleep 0.1
done

if [[ -e "$DEVICE_PATH" ]]; then
  echo "unload: ${DEVICE_PATH} still exists after rmmod" >&2
  exit 1
fi

if [[ "$QUIET" -eq 0 ]]; then
  echo "unload: ${MODULE_NAME} unloaded"
  dmesg 2>/dev/null | grep 'ringbuf_char:' | tail -20 || true
fi

:
