#!/usr/bin/env python3
"""Random sample of reached mutants that no oracle killed, for a hand check (mutation/DESIGN.md, part 4).

A mutant is in the population when its site ran on at least one arm (reach.json) and no oracle
saw any change on any run. The sample (seed fixed) is printed with each mutant's change and the
surrounding source lines, so each can be classified by reading the code:

  equivalent     the change cannot alter behaviour on any input
  not exercised  the change can alter behaviour, but no input in the reduced suite makes it do so
                 (for example, a check that only matters for a failure kind the suite does not inject)

Usage (lab): python3 mutation/equivalence_sample.py --runs ~/cbo/mutruns/runs --vendor ../_vendor [--n 30]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from per_arm import arm_of
from score import effective, verdicts

SEED = 20261008


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--vendor", type=Path, required=True)
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    reach = json.loads((Path(__file__).resolve().parent / "out" / "reach.json").read_text())
    refs = {d.name[4:]: {r["scenario_id"]: r for r in json.loads((d / "done.json").read_text())["runs"]} for d in a.runs.glob("REF-*")}
    population = []
    for d in sorted(a.runs.glob("M1-*")):
        res = json.loads((d / "done.json").read_text())
        m = res["mutant"]
        if res["build"] != "ok" or any(r["status"] != "ok" for r in res["runs"]):
            continue
        lib_ver = f"{m['library']}-{m['version']}"
        reached = any(m["site_id"] in sites for sites in reach.get(lib_ver, {}).get("reached", {}).values())
        if not reached:
            continue
        ref = refs[lib_ver]
        changed = any(verdicts(effective(r, ref[r["scenario_id"]])) != verdicts(ref[r["scenario_id"]]) for r in res["runs"])
        if not changed:
            population.append(m)
    rng = random.Random(SEED)
    sample = rng.sample(population, min(a.n, len(population)))
    print(f"population (reached, killed by no oracle): {len(population)}; sample: {len(sample)} (seed {SEED})\n")
    roots = {"gmrtd": lambda v: a.vendor / f"gmrtd-{v}", "jmrtd": lambda v: a.vendor / "jmrtd-sources-0.8.9",
             "emrtd-dotnet": lambda v: a.vendor / "emrtd-dotnet", "dmrtd": lambda v: a.vendor / "dmrtd"}
    for m in sample:
        path = roots[m["library"]](m["version"]) / m["file"]
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        lo, hi = max(0, m["line"] - 6), min(len(lines), m["line"] + 8)
        print(f"=== {m['mutant_id']} {m['library']} {m['file']}:{m['line']} {m['operator']} step {m['step']}")
        print(f"    change: {m['original'][:120]!r} -> {m['replacement'][:80]!r}")
        for i in range(lo, hi):
            print(f"    {i + 1:5d}{'>' if i + 1 == m['line'] else ' '} {lines[i][:140]}")
        print()


if __name__ == "__main__":
    main()
