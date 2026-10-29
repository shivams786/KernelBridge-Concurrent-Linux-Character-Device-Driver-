#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
trap 'bash "${ROOT_DIR}/scripts/unload.sh" --quiet || true' EXIT
cd "$ROOT_DIR"
make module userspace
bash scripts/reload.sh buffer_capacity=256
if [[ -n "${CONTRACT_OUTPUT:-}" ]]; then
  OUTPUT="$CONTRACT_OUTPUT"
  mkdir "$OUTPUT"
else
  OUTPUT="$(mktemp -d "${TMPDIR:-/tmp}/ringbuf-contract.XXXXXXXX")"
fi
echo "Contract evidence: $OUTPUT/run"
timeout 30 python3 -m lab.runner --backend device --exclusive --seed 42 \
  --steps 300 --output "$OUTPUT/run"
timeout 10 python3 -m lab.runner --backend device --exclusive --seed 42 \
  --steps 12 --workers 3 --output "$OUTPUT/concurrent"
