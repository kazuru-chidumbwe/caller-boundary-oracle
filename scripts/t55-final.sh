#!/usr/bin/env bash
# T55: the single final evaluation at the release commit (Testbed A). Every number of Section 5.2 and Table 9 is
# regenerated from this run. Held-out entries (passauf) are verified and their mismatches reported as results
# (held-out-mismatches.txt); any other mismatch fails the run.
# Progress: ~/cbo/t55.progress. Stop: kill $(cat ~/cbo/t55.pid)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
P=~/cbo/t55.progress
echo $$ > ~/cbo/t55.pid
st() { echo "[$(date -u +%H:%M:%S)] $*" >> "$P"; }
PATH="/usr/local/go/bin:$PATH"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then PATH="$ROOT/.venv/bin:$PATH"; fi
export PATH GOTOOLCHAIN=local
C=$(git rev-parse --short HEAD)
st "start: harness $C, dirty=$(git status --porcelain | wc -l)"
make test > ~/cbo/t55-test.log 2>&1 && st "tests pass" || { st "TESTS FAILED: stopped"; exit 1; }
for suite in pace ca-aa controls independent independent-repeat; do
  if SUITES=$suite bash scripts/evaluate.sh > ~/cbo/t55-$suite.log 2>&1; then
    st "$suite: all entries verify; held-out mismatches: $(grep -c '^HELD-OUT MISMATCH' ~/cbo/t55-$suite.log)"
  else
    st "$suite: FAILED ($(grep -c '^VERIFY FAIL' ~/cbo/t55-$suite.log) mismatches outside the held-out entries): see t55-$suite.log"
  fi
done
# WebAuthn arm from the checkout where its drivers are built, moved to the same commit
WA=~/cbo/cbo-wa
git -C "$WA" fetch -q /tmp/cbo.bundle main && git -C "$WA" checkout -q FETCH_HEAD && st "WebAuthn checkout at $(git -C "$WA" rev-parse --short HEAD)"
OUT=~/cbo/t55-webauthn
rm -rf "$OUT"; mkdir -p "$OUT"
( cd "$WA" && VENDOR_DIR=~/cbo/_vendor ~/cbo/_vendor/webauthn-venv/bin/python webauthn/run.py \
    --drivers webauthn/heldout/drivers-heldout.json --out "$OUT/heldout" --expectations webauthn/heldout/expectations.json > "$OUT/heldout.log" 2>&1 )
st "WebAuthn held-out and development cases: $(tail -1 "$OUT/heldout/VERIFY.txt" 2>/dev/null)"
st "T55 ALL DONE"
