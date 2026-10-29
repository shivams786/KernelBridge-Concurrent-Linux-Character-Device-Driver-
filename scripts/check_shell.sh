#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$#" -eq 0 ]]; then
  set -- "$ROOT_DIR"/scripts/*.sh "$ROOT_DIR"/tests/*.sh
fi
for script in "$@"; do
  bash -n "$script"
done
