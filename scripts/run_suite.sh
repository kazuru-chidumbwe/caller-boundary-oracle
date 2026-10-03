#!/usr/bin/env bash
# Run one suite manifest (default: smoke) and verify it without pipeline gates.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then PATH="$ROOT/.venv/bin:$PATH"; fi
export GOTOOLCHAIN="${GOTOOLCHAIN:-local}"
for env_file in "$ROOT/../_vendor/vsmartcard.env" "$ROOT/../_vendor/dotnet.env" "$ROOT/../_vendor/dart.env"; do
  # shellcheck source=/dev/null
  if [[ -f "$env_file" ]]; then source "$env_file"; fi
done

MANIFEST="${MANIFEST:-suites/smoke.json}"
SUITE_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['suite_id'])" "$MANIFEST")"
LOG_DIR="${LOG_DIR:-logs/suite-${SUITE_ID}-$(date -u +%Y%m%dT%H%M%SZ)}"
python3 classifier/run_suite.py --manifest "$MANIFEST" --log-dir "$LOG_DIR"
python3 classifier/verify_manifest.py "$LOG_DIR" --manifest "$MANIFEST" --no-pipeline
echo "SUITE OK ($LOG_DIR)"
