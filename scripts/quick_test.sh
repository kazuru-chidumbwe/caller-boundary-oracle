#!/usr/bin/env bash
# Smoke: one PACE profile across every arm, with expected outcomes enforced.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then PATH="$ROOT/.venv/bin:$PATH"; fi
export GOTOOLCHAIN="${GOTOOLCHAIN:-local}"
for env_file in "$ROOT/../_vendor/vsmartcard.env" "$ROOT/../_vendor/dotnet.env" "$ROOT/../_vendor/dart.env"; do
  # shellcheck source=/dev/null
  if [[ -f "$env_file" ]]; then source "$env_file"; fi
done

LOG_DIR="${LOG_DIR:-logs/smoke-$(date -u +%Y%m%dT%H%M%SZ)}"
python3 classifier/run_suite.py --manifest suites/smoke.json --log-dir "$LOG_DIR"
python3 classifier/verify_manifest.py "$LOG_DIR" --manifest suites/smoke.json --no-pipeline
echo "SMOKE OK ($LOG_DIR)"
