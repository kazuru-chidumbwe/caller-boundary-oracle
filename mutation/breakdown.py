"""Exploratory: written on 8 Oct 2026 after the first scoring, not part of the frozen design (mutation/DESIGN.md, change 7).

delivered: fault delivered in both the reference and the mutant run (failure reporting can change)
delivery:  applicability changed (not_applicable on one side only)
control:   no fault injected (controls, positive control)
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[2]) / "mutation"))
from score import verdicts, effective  # noqa: E402

runs = Path(sys.argv[1])
refs = {}
for d in runs.glob("REF-*"):
    refs[d.name[4:]] = {r["scenario_id"]: r for r in json.loads((d / "done.json").read_text())["runs"]}

SCORED = {"silent", "status_only", "surfaced"}
per_type = defaultdict(lambda: Counter())
trans = Counter()
trans_seen = defaultdict(Counter)
mut_delivered = Counter()
for d in sorted(runs.glob("M1-*")):
    res = json.loads((d / "done.json").read_text())
    if res["build"] != "ok":
        continue
    m = res["mutant"]
    ref = refs[f"{m['library']}-{m['version']}"]
    if any(r["status"] != "ok" for r in res["runs"]):
        continue
    kinds = {"delivered": set(), "delivery": set(), "control": set()}
    for run in res["runs"]:
        r0 = ref[run["scenario_id"]]
        run = effective(run, r0)
        v, v0 = verdicts(run), verdicts(r0)
        is_control = "CTRL-" in run["scenario_id"] or "pace-success" in run["scenario_id"]
        if is_control:
            kind = "control"
        elif v0["cbo"] in SCORED and v["cbo"] in SCORED:
            kind = "delivered"
        else:
            kind = "delivery"
        for o in ("cbo", "any_error", "output", "p4"):
            if v[o] != v0[o]:
                kinds[kind].add(o)
        if kind == "delivered" and v["cbo"] != v0["cbo"]:
            t = (v0["cbo"], v["cbo"])
            trans[t] += 1
            for o in ("any_error", "output", "p4"):
                if v[o] != v0[o]:
                    trans_seen[t][o] += 1
    for kind, os_ in kinds.items():
        if os_:
            per_type[kind]["any"] += 1
            for o in os_:
                per_type[kind][o] += 1
    if "cbo" in kinds["delivered"]:
        mut_delivered[m["library"]] += 1

print("Mutants with a change, by run type and oracle (a mutant can appear in several types):")
for kind in ("delivered", "delivery", "control"):
    print(f"  {kind:9}", dict(per_type[kind]))
print("\nDelivered runs whose CBO outcome changed (reference -> mutant): runs, and how many each baseline also saw")
for t, n in trans.most_common():
    print(f"  {t[0]:>11} -> {t[1]:<11} {n:4}   seen by any_error {trans_seen[t]['any_error']}, output {trans_seen[t]['output']}, p4 {trans_seen[t]['p4']}")
print("\nMutants with a delivered-run outcome change, by library:", dict(mut_delivered))
