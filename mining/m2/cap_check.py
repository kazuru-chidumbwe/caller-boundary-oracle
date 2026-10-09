#!/usr/bin/env python3
"""Check on the screening (screen_m2.py): repositories marked not_included after searching only 400 of their source
files are searched in full with GitHub code search (repo-scoped queries "doPACE" and "doBAC"; JMRTD only).
A hit means the cap hid a call and the repository is re-screened by hand; no hit confirms not_included.
Output: screen/cap-check.csv. Usage: python mining/m2/cap_check.py   (needs an authenticated gh)
"""
import csv
import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = [r for r in csv.DictReader(open(HERE / "screen/screen.csv", encoding="utf-8"))
        if r["decision"] == "not_included" and "+ 400 of" in r["searched"]]
out = []
for r in rows:
    hits = {}
    for term in ("doPACE", "doBAC"):
        for attempt in range(5):
            p = subprocess.run(["gh", "api", "-X", "GET", "search/code", "-f", f"q={term} repo:{r['repo']}"],
                               capture_output=True, text=True, encoding="utf-8")
            if p.returncode == 0:
                hits[term] = json.loads(p.stdout).get("total_count", 0)
                break
            time.sleep(30)
        else:
            hits[term] = "error"
        time.sleep(2.2)   # code search allows 30 requests a minute
    out.append({"repo": r["repo"], "library": r["library"], **{f"hits_{k}": v for k, v in hits.items()}})
    print(out[-1], flush=True)
with open(HERE / "screen/cap-check.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["repo", "library", "hits_doPACE", "hits_doBAC"])
    w.writeheader()
    w.writerows(out)
print("repositories:", len(out), "with any hit:", sum(1 for o in out if any(v not in (0, "error") for k, v in o.items() if k.startswith("hits"))))
