#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
printf '#!/bin/bash\ntrue\n' > "$TMP_DIR/valid.sh"
printf '#!/bin/bash\nif then\n' > "$TMP_DIR/invalid.sh"
bash "$ROOT_DIR/scripts/check_shell.sh" "$TMP_DIR/valid.sh"
if bash "$ROOT_DIR/scripts/check_shell.sh" "$TMP_DIR/valid.sh" \
  "$TMP_DIR/invalid.sh" > "$TMP_DIR/output" 2>&1; then
  echo "FAIL: syntax error in second script was missed" >&2
  exit 1
fi
echo "PASS: syntax errors after the first script are detected"
