#!/usr/bin/env bash
set -euo pipefail
ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
TMP=/tmp/monthly-c2-contract
cd "$ROOT"
git fetch origin main --depth=1
rm -rf "$TMP"
git worktree add --detach "$TMP" origin/main
cp scripts/build_monthly_territorial.py "$TMP/scripts/build_monthly_territorial.py"
cp scripts/validate_monthly_c2_contract.py "$TMP/scripts/validate_monthly_c2_contract.py"
cd "$TMP"
PYTHONPATH=. python scripts/validate_monthly_c2_contract.py
