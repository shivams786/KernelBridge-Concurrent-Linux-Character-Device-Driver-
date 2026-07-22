#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rm -rf "${ROOT_DIR}/tests/logs"
rm -f "${ROOT_DIR}"/*.o
rm -f "${ROOT_DIR}"/*.ko
rm -f "${ROOT_DIR}"/*.mod
rm -f "${ROOT_DIR}"/*.mod.c
rm -f "${ROOT_DIR}"/*.order
rm -f "${ROOT_DIR}"/*.symvers
rm -f "${ROOT_DIR}"/.*.cmd
rm -rf "${ROOT_DIR}/.tmp_versions"

echo "clean: removed generated project artifacts"
