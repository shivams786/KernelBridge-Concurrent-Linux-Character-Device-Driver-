#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
trap 'bash "${ROOT_DIR}/scripts/unload.sh" --quiet || true' EXIT
make -C "$ROOT_DIR" module userspace
bash "${ROOT_DIR}/scripts/reload.sh" buffer_capacity=256
timeout 20 "${ROOT_DIR}/userspace/regression_test"
