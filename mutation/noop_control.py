#!/usr/bin/env python3
"""Negative control: the probe builds as neutral mutants (mutation/DESIGN.md, change 11).

The reachability probe (probe.py) adds one statement per site that only prints a marker to the
error stream. Those builds are therefore neutral mutants of every probed site at once. No oracle
may report a difference between a probe run and the unmutated reference run of the same entry.

Usage: python3 mutation/noop_control.py --probe ~/cbo/mutprobe/runs --runs ~/cbo/mutruns/runs
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from score import verdicts

SKIP = {"artifact-manifest.json", "environment.json"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probe", type=Path, required=True)
    ap.add_argument("--runs", type=Path, required=True)
    a = ap.parse_args()
    total, diffs, missing = 0, Counter(), []
    for lib_dir in sorted(a.probe.iterdir()):
        ref = {r["scenario_id"]: r for r in json.loads((a.runs / f"REF-{lib_dir.name}" / "done.json").read_text())["runs"]}
        for run_dir in sorted(lib_dir.iterdir()):
            arts = [p for p in run_dir.glob("*.json") if p.name not in SKIP]
            if len(arts) != 1:
                missing.append(run_dir.name)
                continue
            art = json.loads(arts[0].read_text())
            probe = {"outcome": art.get("outcome"), "observation": art.get("observation"),
                     "access_control": art.get("access_control"), "bac_success": art.get("bac_success")}
            v, v0 = verdicts(probe), verdicts(ref[run_dir.name])
            total += 1
            for o in v:
                if v[o] != v0[o]:
                    diffs[(lib_dir.name, o)] += 1
    print(f"probe runs compared with the reference: {total}; runs without an artifact: {len(missing)} {missing[:5]}")
    print("differences by library version and oracle:", dict(diffs) if diffs else "none")


if __name__ == "__main__":
    main()
