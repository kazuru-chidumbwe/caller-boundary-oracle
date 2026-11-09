#!/usr/bin/env bash
# H1: the full evaluation at the frozen harness commit (Testbed A). T55's suites plus every suite added since
# (U2 passauf v0.2.1 held-out, U6 JMRTD step-4 bodies, U7 BAC-only chip) and the WebAuthn held-out cases for
# fido2-net-lib 4.2.0 and 4.3.2 (U3). Table 9, Figures 2 to 6 and every 5.2 number are regenerated from this run.
# Held-out entries are verified and their mismatches reported as results; any other mismatch fails that suite.
# Progress: ~/cbo/h1.progress; done flag ~/cbo/H1-DONE. Stop: kill $(cat ~/cbo/h1.pid)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
P=~/cbo/h1.progress; OUT=~/cbo/h1-run
echo $$ > ~/cbo/h1.pid; : > "$P"; rm -f ~/cbo/H1-DONE; mkdir -p "$OUT"
st() { echo "[$(date -u +%FT%TZ)] $*" >> "$P"; }
PATH="/usr/local/go/bin:$PATH"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then PATH="$ROOT/.venv/bin:$PATH"; fi
export PATH GOTOOLCHAIN=go1.26.10
C=$(git rev-parse --short HEAD)
st "start: harness $C, dirty=$(git status --porcelain | grep -v '^??' | wc -l), $(go version)"
st "gofmt: [$(gofmt -l internal guard cmd simulator | tr '\n' ' ')] vet: $(go vet ./internal/... ./guard/... ./cmd/... >/dev/null 2>&1 && echo ok || echo FAIL)"
make test > "$OUT/test.log" 2>&1 && st "tests pass" || { st "TESTS FAILED: stopped"; exit 1; }
rm -f bin/chip-serve bin/gmrtd-read drivers/jmrtd/target/jmrtd-driver-0.1.0.jar
for suite in pace ca-aa controls independent independent-repeat u6-jmrtd u7-bac heldout-passauf-v021; do
  if SUITES=$suite bash scripts/evaluate.sh > "$OUT/$suite.log" 2>&1; then
    st "$suite: all entries verify; held-out mismatches: $(grep -c '^HELD-OUT MISMATCH' "$OUT/$suite.log")"
  else
    st "$suite: FAILED ($(grep -c '^VERIFY FAIL' "$OUT/$suite.log") mismatches outside the held-out entries): see $OUT/$suite.log"
  fi
done
# WebAuthn arm from the checkout where its drivers are built, moved to the same commit
WA=~/cbo/cbo-wa
git -C "$WA" fetch -q "$ROOT" HEAD && git -C "$WA" checkout -q FETCH_HEAD && st "WebAuthn checkout at $(git -C "$WA" rev-parse --short HEAD)"
W="$OUT/webauthn"; rm -rf "$W"; mkdir -p "$W"
( cd "$WA" && VENDOR_DIR=~/cbo/_vendor ~/cbo/_vendor/webauthn-venv/bin/python webauthn/run.py \
    --drivers webauthn/heldout/drivers-heldout.json --out "$W/heldout" --expectations webauthn/heldout/expectations.json > "$W/heldout.log" 2>&1 )
st "WebAuthn held-out and development cases: $(tail -1 "$W/heldout/VERIFY.txt" 2>/dev/null)"
# fido2-net-lib 4.2.0 and 4.3.2 side by side, the U3 driver builds
python3 -c 'import json,sys; json.dump(json.load(open(sys.argv[1]))["drivers"], open(sys.argv[2],"w"), indent=1)' \
  ~/cbo/u3-run/RUN.json "$W/drivers-u3.json"
( cd "$WA" && VENDOR_DIR=~/cbo/_vendor ~/cbo/_vendor/webauthn-venv/bin/python webauthn/run.py \
    --drivers "$W/drivers-u3.json" --out "$W/u3" --expectations webauthn/heldout/expectations.json > "$W/u3.log" 2>&1 )
st "WebAuthn fido2-net-lib 4.2.0 and 4.3.2: $(tail -1 "$W/u3/VERIFY.txt" 2>/dev/null)"
st "post: dirty=$(git status --porcelain | grep -v '^??' | wc -l)"
st "H1 ALL DONE"; touch ~/cbo/H1-DONE
