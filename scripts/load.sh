#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODULE_NAME="shivam_char"
MODULE_PATH="${ROOT_DIR}/${MODULE_NAME}.ko"
DEVICE_PATH="/dev/${MODULE_NAME}"
FORCE_UNLOAD=0
APPLY_CHMOD=0
PARAMS=()

usage() {
  cat <<'USAGE'
Usage: sudo bash scripts/load.sh [--force] [--chmod] [module_param=value ...]

Options:
  --force   unload an existing shivam_char module before loading
  --chmod   apply chmod 666 to /dev/shivam_char for disposable local testing
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --force|--reload)
      FORCE_UNLOAD=1
      ;;
    --chmod)
      APPLY_CHMOD=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      PARAMS+=("$arg")
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "load: loading kernel modules requires root; rerun with sudo" >&2
  exit 1
fi

if [[ ! -f "$MODULE_PATH" ]]; then
  echo "load: missing ${MODULE_PATH}; run 'make module' first" >&2
  exit 1
fi

if lsmod | awk '{print $1}' | grep -qx "$MODULE_NAME"; then
  if [[ "$FORCE_UNLOAD" -eq 1 ]]; then
    echo "load: unloading existing ${MODULE_NAME}"
    bash "${ROOT_DIR}/scripts/unload.sh" --quiet
  else
    echo "load: ${MODULE_NAME} is already loaded; pass --force to reload" >&2
    exit 1
  fi
fi

echo "load: inserting ${MODULE_PATH}"
insmod "$MODULE_PATH" "${PARAMS[@]}"

if ! lsmod | awk '{print $1}' | grep -qx "$MODULE_NAME"; then
  echo "load: ${MODULE_NAME} did not appear in lsmod" >&2
  exit 1
fi

for _ in $(seq 1 50); do
  if [[ -e "$DEVICE_PATH" ]]; then
    break
  fi
  sleep 0.1
done

if [[ ! -e "$DEVICE_PATH" ]]; then
  echo "load: ${DEVICE_PATH} was not created" >&2
  exit 1
fi

if [[ "$APPLY_CHMOD" -eq 1 ]]; then
  echo "load: applying chmod 666 for disposable local testing"
  chmod 666 "$DEVICE_PATH"
fi

echo "load: module is loaded"
if command -v stat >/dev/null 2>&1; then
  stat -c 'load: device %n permissions=%A owner=%U group=%G major_minor=%t:%T' \
    "$DEVICE_PATH"
else
  ls -l "$DEVICE_PATH"
fi

echo "load: recent driver logs"
dmesg 2>/dev/null | grep 'shivam_char:' | tail -20 || true

