#!/bin/bash
# T20 real-chip session on the run host (Testbed A). Usage, from the harness root, detached:
#   scripts/t20-real-session.sh dry    three reads (JMRTD propagate, correct MRZ) to check the NFC link
#   scripts/t20-real-session.sh full   the 26 entries of suites/real-chip.json, then cleanup
#   scripts/t20-real-session.sh clean  delete the MRZ file, generated profiles and raw run files
# The MRZ comes from ~/.cbo-real-mrz (one line CBO_REAL_MRZ=DOC:YYMMDD:YYMMDD), written by the document
# holder on the host. Nothing here prints it. Kept: outcome fields only (OUT/OUTCOMES.json) and progress.
set -uo pipefail
MODE="${1:-dry}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
BASE=~/cbo/t20-real; P=$BASE/progress.txt; L=$BASE/session.log; HUBST=$BASE/hub.json
mkdir -p $BASE; touch $P
log(){ echo "[$(date +%H:%M:%S)] $*" >> $P; }
cleanup(){
  rm -f ~/.cbo-real-mrz; rm -rf "$ROOT/profiles/real/local" $BASE/runs-*; rm -f $L
  log "cleanup: MRZ file, generated profiles, raw runs and session log deleted"
}
if [[ "$MODE" == clean ]]; then cleanup; exit 0; fi
export PATH=/usr/local/go/bin:$PATH GOTOOLCHAIN=go1.26.10
for f in ../_vendor/vsmartcard.env ../_vendor/dotnet.env ../_vendor/dart.env; do [ -f $f ] && source $f; done
[ -f ~/.cbo-real-mrz ] || { log "no ~/.cbo-real-mrz: the document holder writes it first"; exit 1; }
set -a; source ~/.cbo-real-mrz; set +a
python3 profiles/generate_real_profiles.py --real >> $L 2>&1 || { log "profile generation failed"; exit 1; }
log "start $MODE: $(git rev-parse --short HEAD) dirty=$(git status --porcelain | grep -v '^??' | wc -l)"

if ! pgrep -f "phone_hub.py --phone-host" >/dev/null; then
  setsid nohup python3 tools/vsmartcard/phone_hub.py --phone-host 192.0.2.48 --status $HUBST </dev/null >> $L 2>&1 &
  sleep 1
fi
for i in $(seq 1 120); do grep -q '"phone_connected": true' $HUBST 2>/dev/null && break; sleep 5; done
grep -q '"phone_connected": true' $HUBST || { log "phone did not connect within 10 minutes"; exit 1; }
log "phone connected: $(cat $HUBST)"

OUT=$BASE/runs-$MODE-$(date -u +%Y%m%dT%H%M%SZ)
if [[ "$MODE" == dry ]]; then
  python3 - > $BASE/dry-manifest.json <<'PY'
import json
d = json.load(open("suites/real-chip.json"))
e = [x for x in d["entries"] if x["test_case"] == "REAL-pace-success" and x["library"] == "jmrtd" and x["variant"] == "propagate"][0]
print(json.dumps({"suite_id": "real-dry", "description": "T20 link check", "seed": 1, "n": 3, "entries": [dict(e, n=3)]}))
PY
  MAN=$BASE/dry-manifest.json
else
  MAN=suites/real-chip.json
fi
python3 classifier/run_suite.py --manifest $MAN --log-dir $OUT >> $L 2>&1; RC=$?
python3 - "$OUT" "$MAN" > $BASE/OUTCOMES-$MODE.json <<'PY'
import json, glob, sys
out, man = sys.argv[1], sys.argv[2]
exp = {(e["test_case"], e["library"], e["variant"]): e.get("expect_outcome") for e in json.load(open(man))["entries"]}
rows = []
for f in sorted(glob.glob(out + "/*.json")):
    r = json.load(open(f))
    if "test_case" not in r:
        continue
    want = exp.get((r["test_case"], r["library"], r["variant"]))
    rows.append({"test_case": r["test_case"], "library": r["library"], "variant": r["variant"],
                 "outcome": r["outcome"], "observation": r.get("observation"),
                 "expected": want, "held": want == r["outcome"]})
print(json.dumps({"runs": len(rows), "held": sum(x["held"] for x in rows), "rows": rows}, indent=1))
PY
log "$MODE done rc=$RC: $(python3 -c "import json;d=json.load(open('$BASE/OUTCOMES-$MODE.json'));print(d['runs'],'runs,',d['held'],'as expected')")"
log "hub: $(cat $HUBST)"
if [[ "$MODE" == full ]]; then cleanup; fi
log "$MODE DONE"
