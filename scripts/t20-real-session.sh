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

# Some chips add a growing delay after failed access attempts. Full mode therefore runs each library's
# correct read and then its wrong-key read, waits WRONG_WAIT seconds before every wrong-key read, and stops
# ("chip slowing") when a wrong-key run's slowest chip reply exceeds SLOW_MS; that run is set aside, not scored,
# and a later start resumes at the first entry without a result.
WRONG_WAIT="${WRONG_WAIT:-30}"; SLOW_MS="${SLOW_MS:-3000}"
OUT=$BASE/runs-$MODE; [[ "$MODE" == dry ]] && OUT=$BASE/runs-dry-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p $OUT
python3 - "$MODE" > $BASE/order.json <<'PY'
import json, sys
d = json.load(open("suites/real-chip.json"))["entries"]
if sys.argv[1] == "dry":
    e = [x for x in d if x["test_case"] == "REAL-pace-success" and x["library"] == "jmrtd" and x["variant"] == "propagate"][0]
    order = [dict(e, scenario_id=f"{e['scenario_id']}-dry{i}") for i in (1, 2, 3)]
else:
    ok = [x for x in d if x["test_case"] == "REAL-pace-success"]
    bad = {(x["library"], x["variant"]): x for x in d if x["test_case"] == "REAL-pace-wrong-mrz"}
    order = [y for x in ok for y in (x, bad[(x["library"], x["variant"])])]
print(json.dumps(order))
PY
RC=0
N=$(python3 -c "import json;print(len(json.load(open('$BASE/order.json'))))")
for i in $(seq 0 $((N-1))); do
  python3 -c "import json;e=json.load(open('$BASE/order.json'))[$i];json.dump({'suite_id':'real-chip','description':'T20','seed':1,'n':1,'entries':[e]},open('$BASE/one.json','w'));print(e['scenario_id']);print(e['test_case'])" > $BASE/one.txt
  SID=$(sed -n 1p $BASE/one.txt); TC=$(sed -n 2p $BASE/one.txt)
  if ls $OUT/$SID/*.json >/dev/null 2>&1; then continue; fi   # resume: already done
  if [[ "$TC" == REAL-pace-wrong-mrz ]]; then sleep $WRONG_WAIT; fi
  python3 classifier/run_suite.py --manifest $BASE/one.json --log-dir $OUT/$SID >> $L 2>&1 || RC=$?
  MS=$(python3 -c "import json;print(json.load(open('$HUBST')).get('last_run_max_reply_ms',0))")
  echo -e "$SID\t$MS" >> $OUT/latency.tsv
  if [[ "$TC" == REAL-pace-wrong-mrz && "$MS" -gt "$SLOW_MS" ]]; then
    mv $OUT/$SID $OUT/$SID-SETASIDE-slow-${MS}ms
    log "chip slowing: $SID slowest reply ${MS} ms; stopped after $i of $N entries; rest the passport, then start again to resume"
    exit 3
  fi
done
python3 - "$OUT" > $BASE/OUTCOMES-$MODE.json <<'PY'
import json, glob, sys
out = sys.argv[1]
exp = {(e["test_case"], e["library"], e["variant"]): e.get("expect_outcome")
       for e in json.load(open("suites/real-chip.json"))["entries"]}
lat = dict(l.rstrip("\n").split("\t") for l in open(out + "/latency.tsv")) if glob.glob(out + "/latency.tsv") else {}
rows = []
for f in sorted(glob.glob(out + "/*/*.json")):
    if "SETASIDE" in f:
        continue
    r = json.load(open(f))
    if "test_case" not in r:
        continue
    want = exp.get((r["test_case"], r["library"], r["variant"]))
    sid = f.split("/")[-2]
    rows.append({"test_case": r["test_case"], "library": r["library"], "variant": r["variant"],
                 "outcome": r["outcome"], "observation": r.get("observation"), "slowest_reply_ms": lat.get(sid),
                 "expected": want, "held": want == r["outcome"]})
print(json.dumps({"runs": len(rows), "held": sum(x["held"] for x in rows), "rows": rows}, indent=1))
PY
log "$MODE done rc=$RC: $(python3 -c "import json;d=json.load(open('$BASE/OUTCOMES-$MODE.json'));print(d['runs'],'runs,',d['held'],'as expected')")"
log "hub: $(cat $HUBST)"
if [[ "$MODE" == full ]]; then cleanup; fi
log "$MODE DONE"
