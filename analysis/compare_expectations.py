#!/usr/bin/env python3
"""Compare every run of a suite with its pre-registered expectation (expect_outcome, expect_observation).

Usage: python3 analysis/compare_expectations.py LOG_DIR MANIFEST [--out OUT.json]
Prints held / not-held counts per cell and lists every run that does not match, with its observation,
fault point, access control and error text, so that each mismatch can be reported as it is.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir", type=Path)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    entries = {(e["test_case"], e["library"], e["variant"]): e
               for e in json.loads(a.manifest.read_text(encoding="utf-8"))["entries"]}
    skip = {"artifact-manifest.json", "environment.json"}
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(a.log_dir.glob("*.json"))
            if p.name not in skip and not p.name.startswith("summary")]
    per = defaultdict(Counter)
    misses, unmatched = [], []
    for r in runs:
        e = entries.get((r["test_case"], r["library"], r["variant"]))
        if e is None:
            unmatched.append(r["run_id"])
            continue
        want = e["expect_outcome"]
        ok = r["outcome"] in (want if isinstance(want, list) else [want])
        for k, v in (e.get("expect_observation") or {}).items():
            ok = ok and r["observation"].get(k) == v
        per[r["test_case"]]["held" if ok else "not_held"] += 1
        if not ok:
            misses.append({"test_case": r["test_case"], "expected": want, "expect_observation": e.get("expect_observation"),
                           "outcome": r["outcome"], "observation": r["observation"], "fault_point": r.get("fault_point"),
                           "access_control": r.get("access_control"), "read_err": (r.get("read_err") or "")[:200],
                           "hang": r.get("hang")})
    cells_held = sum(1 for c in per.values() if c["not_held"] == 0)
    summary = {"runs": len(runs), "unmatched_runs": len(unmatched), "cells": len(per), "cells_all_held": cells_held,
               "runs_held": sum(c["held"] for c in per.values()), "runs_not_held": sum(c["not_held"] for c in per.values()),
               "outcomes": dict(Counter(r["outcome"] for r in runs)),
               "hangs": sum(1 for r in runs if r.get("hang")),
               "not_held_cells": sorted({m["test_case"] for m in misses})}
    out = {"summary": summary, "misses": misses}
    print(json.dumps(out, indent=1)[:6000])
    if a.out:
        a.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
