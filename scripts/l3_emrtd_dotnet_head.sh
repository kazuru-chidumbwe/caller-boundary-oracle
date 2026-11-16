#!/usr/bin/env bash
# L3: emrtd-dotnet entries of pace, controls, independent and independent-repeat on a newer emrtd-dotnet commit,
# verified against the unchanged expectations of those suites. Prediction (16 Nov 2026, before the run): every
# entry verifies, because 0433b3a...bdfddd0 changes only offline dump parsing (DocumentReader.Parse, LoadDump),
# DG11 name display and NuGet packaging; TryPace, BAC and the access-control field are unchanged.
#
# Usage (lab): EMRTD_DOTNET_COMMIT=bdfddd0 OUT=... scripts/l3_emrtd_dotnet_head.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
C="${EMRTD_DOTNET_COMMIT:?}"; OUT="${OUT:?}"
V="$ROOT/../_vendor"
WT="$V/emrtd-dotnet-$C"
git -C "$V/emrtd-dotnet" fetch -q origin || true
[ -d "$WT" ] || git -C "$V/emrtd-dotnet" worktree add -q --detach "$WT" "$C"
export EmrtdDotnetDir="$WT"
echo "emrtd-dotnet at $(git -C "$WT" rev-parse --short HEAD)"
rm -rf drivers/dotnet/bin drivers/dotnet/obj
mkdir -p "$OUT/suites"
for s in pace controls independent independent-repeat; do
  python3 - "$s" "$OUT/suites/l3-$s.json" <<'PY'
import json, sys
s, out = sys.argv[1], sys.argv[2]
d = json.load(open(f"suites/{s}.json"))
d["suite_id"] = f"l3-{s}"
d["entries"] = [e for e in d["entries"] if e["library"] == "emrtd-dotnet"]
json.dump(d, open(out, "w"), indent=1)
print(s, len(d["entries"]), "emrtd-dotnet entries")
PY
  MANIFEST="$OUT/suites/l3-$s.json" LOG_DIR="$OUT/l3-$s" bash scripts/run_suite.sh > "$OUT/l3-$s.log" 2>&1 \
    && echo "$s: SUITE OK" || echo "$s: VERIFY FAILED (see $OUT/l3-$s.log)"
done
python3 -c "
import json,glob,sys,collections
recs=[json.load(open(f)) for f in glob.glob(sys.argv[1]+'/l3-*/**/*.json', recursive=True)]
c=collections.Counter(r['provenance'].get('emrtd_dotnet_commit','none')[:7] for r in recs if isinstance(r,dict) and 'provenance' in r)
print('emrtd_dotnet_commit in run records:', dict(c))" "$OUT"
