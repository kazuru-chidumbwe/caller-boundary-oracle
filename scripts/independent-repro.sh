#!/usr/bin/env bash
# Reproduce the evaluation from a fresh copy of the tree with freshly fetched pins.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPRO="${REPRO_ROOT:-/tmp/caller-boundary-oracle-repro}"

rm -rf "$REPRO"
mkdir -p "$REPRO"
git -C "$ROOT" archive --format=tar HEAD | (mkdir -p "$REPRO/harness" && tar -x -C "$REPRO/harness")
cd "$REPRO/harness"
git init -q && git add -A && git -c user.name=repro -c user.email=repro@localhost commit -qm repro
VENDOR_DIR="$REPRO/_vendor" bash scripts/bootstrap-vendor.sh
make venv
make evaluate 2>&1 | tee "$REPRO/repro.log"
echo "REPRO OK (log at $REPRO/repro.log)"
