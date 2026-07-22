#!/usr/bin/env bash
set -euo pipefail

INSTALL=0
ASSUME_YES=0
PACKAGES=(
  build-essential
  "linux-headers-$(uname -r)"
  gcc
  make
  libc6-dev
  kmod
  util-linux
  procps
)

log() {
  printf 'setup: %s\n' "$*"
}

usage() {
  cat <<'USAGE'
Usage: bash scripts/setup.sh [--install] [--yes]

Without --install, this script prints the packages needed for an
Ubuntu/Debian development VM and checks whether key tools are present.
With --install, it runs apt-get and must be executed as root.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --install)
      INSTALL=1
      ;;
    --yes|-y)
      ASSUME_YES=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'setup: unknown option: %s\n' "$arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

OS_ID="unknown"
OS_LIKE=""
if [[ -r /etc/os-release ]]; then
  # shellcheck source=/dev/null
  source /etc/os-release
  OS_ID="${ID:-unknown}"
  OS_LIKE="${ID_LIKE:-}"
fi

log "detected OS: ${OS_ID} (${OS_LIKE:-no ID_LIKE})"
log "kernel: $(uname -r)"

if [[ "$OS_ID $OS_LIKE" != *debian* && "$OS_ID $OS_LIKE" != *ubuntu* ]]; then
  cat >&2 <<EOF
setup: this helper only knows how to install packages on Debian/Ubuntu.
setup: install equivalent packages manually:
setup:   ${PACKAGES[*]}
EOF
  exit 1
fi

log "required packages: ${PACKAGES[*]}"

if [[ "$INSTALL" -eq 0 ]]; then
  log "dry run only. To install packages, run:"
  printf '  sudo bash scripts/setup.sh --install --yes\n'
  log "checking common tools"
  for tool in gcc make modinfo lsmod insmod rmmod timeout; do
    if command -v "$tool" >/dev/null 2>&1; then
      printf '  %-10s ok\n' "$tool"
    else
      printf '  %-10s missing\n' "$tool"
    fi
  done
  if [[ -d "/lib/modules/$(uname -r)/build" ]]; then
    log "kernel headers found at /lib/modules/$(uname -r)/build"
  else
    log "kernel headers missing: install linux-headers-$(uname -r)"
  fi
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "setup: --install requires root; rerun with sudo" >&2
  exit 1
fi

APT_FLAGS=()
if [[ "$ASSUME_YES" -eq 1 ]]; then
  APT_FLAGS=(-y)
fi

log "updating apt package metadata"
apt-get update
log "installing build dependencies"
apt-get install "${APT_FLAGS[@]}" "${PACKAGES[@]}"
log "setup complete"

