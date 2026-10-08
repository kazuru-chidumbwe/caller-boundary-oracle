#!/usr/bin/env python3
"""Reduced suite for the mutation baseline (mutation/DESIGN.md, part 2).

Entries are copied from the verified suites, so every entry keeps its expected outcome. Each
entry gets a "step" (PACE, CA, AA or CONTROL); a mutant runs the entries of its own step plus
the CONTROL entries. NFCPassportReader is not part of the mutation study (decision D1).

Usage: python3 mutation/reduced_suite.py   (writes mutation/reduced.json)
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROFILES = {
    "PACE": {
        "PACE-mse-set-at-6a80", "PACE-mse-set-at-6f00", "PACE-mse-set-at-timeout",
        "PACE-general-authenticate-6a80", "PACE-general-authenticate-6f00", "PACE-general-authenticate-timeout",
        "VSC-pace-ga3-6a80",
    },
    "CA": {"CA-mse-set-at-6300", "CA-mse-set-at-6700", "CA-mse-set-at-6a80", "CA-mse-set-at-6f00"},
    "AA": {
        "AA-internal-authenticate-6300", "AA-internal-authenticate-6700",
        "AA-internal-authenticate-6a80", "AA-internal-authenticate-6f00",
    },
    "CONTROL": {"CTRL-bac-only", "CTRL-pace-proprietary-params", "VSC-pace-success"},
}
STEP_OF = {case: step for step, cases in PROFILES.items() for case in cases}
SUITES = ("pace", "ca-aa", "controls", "independent")


def main() -> None:
    entries = []
    for suite in SUITES:
        manifest = json.loads((ROOT / "suites" / f"{suite}.json").read_text(encoding="utf-8"))
        for e in manifest["entries"]:
            step = STEP_OF.get(e["test_case"])
            if step is None or e["library"] == "nfcpassportreader":
                continue
            e = dict(e, step=step, source_suite=suite)
            entries.append(e)
    entries.sort(key=lambda e: (e["library"], e.get("gmrtd_pin", ""), e["step"], e["scenario_id"]))
    out = {
        "suite_id": "mutation-reduced",
        "description": "Reduced suite for the mutation baseline; entries copied from the verified suites.",
        "seed": 1,
        "n": 1,
        "entries": entries,
    }
    path = ROOT / "mutation" / "reduced.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for e in entries:
        k = f"{e['library']} {e['step']}"
        counts[k] = counts.get(k, 0) + 1
    print(f"wrote {path} ({len(entries)} entries)")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")


if __name__ == "__main__":
    main()
