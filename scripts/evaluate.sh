#!/usr/bin/env bash
# Full evaluation: pins, tests, smoke, then every suite with pipeline gates, then publish
# the verified manifests under artifacts/. Any failure stops the run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then PATH="$ROOT/.venv/bin:$PATH"; fi
export GOTOOLCHAIN="${GOTOOLCHAIN:-local}"
for env_file in "$ROOT/../_vendor/vsmartcard.env" "$ROOT/../_vendor/dotnet.env" "$ROOT/../_vendor/dart.env"; do
  # shellcheck source=/dev/null
  if [[ -f "$env_file" ]]; then source "$env_file"; fi
done
SUITES=(${SUITES:-pace ca-aa controls independent independent-repeat})
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STATE="$ROOT/logs/.pipeline-state-$STAMP.json"
mkdir -p logs artifacts

write_state() {
  python3 - "$STATE" "$1" "$2" "$3" <<'PY'
import json, sys
path, tests, smoke, suite = sys.argv[1:5]
json.dump({"tests": tests, "smoke": smoke, "suite_complete": suite == "true"}, open(path, "w"), indent=2)
PY
}

echo "==> [1/4] gmrtd pins"
bash scripts/verify_gmrtd_pin.sh

echo "==> [2/4] tests"
if ! make test; then write_state fail fail false; echo "evaluate: tests failed" >&2; exit 1; fi

echo "==> [3/4] smoke"
if ! bash scripts/quick_test.sh; then write_state pass fail false; echo "evaluate: smoke failed" >&2; exit 1; fi

echo "==> [4/4] suites: ${SUITES[*]}"
COMMIT="$(git rev-parse HEAD)"
for suite in "${SUITES[@]}"; do
  manifest="suites/$suite.json"
  log_dir="logs/suite-$suite-$STAMP"
  if ! python3 classifier/run_suite.py --manifest "$manifest" --log-dir "$log_dir"; then
    write_state pass pass false
    echo "evaluate: suite $suite incomplete" >&2
    exit 1
  fi
  write_state pass pass true
  python3 classifier/aggregate.py --log-dir "$log_dir" --manifest "$manifest" --suite-id "$suite" \
    --suite-seed 1 --pipeline-json "$STATE" > /dev/null
  python3 classifier/verify_manifest.py "$log_dir" --manifest "$manifest"
  cp "$log_dir/artifact-manifest.json" "artifacts/$suite-$COMMIT-artifact-manifest.json"
  cp "$log_dir/summary.md" "artifacts/$suite-$COMMIT-summary.md"
done

echo ""
echo "EVALUATE OK (commit $COMMIT)"
ls -1 artifacts/*-"$COMMIT"-*
