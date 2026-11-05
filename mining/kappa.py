#!/usr/bin/env python3
"""Agreement between coder A and coder B (PROTOCOL.md: agreement and adjudication).

For every variable: the items both coders coded, raw agreement, Cohen's kappa and a 95 per cent confidence
interval (percentile bootstrap over items, 2,000 resamples, random.Random(20261008)). Target 0.7; a variable
below 0.6 has its definition reviewed and both coders recode it. Every disagreement is listed for the
adjudication log.

Usage: python mining/kappa.py --study m1|m2 --a CODER_A.csv --b CODER_B.csv --comparison SHEET [...]
       [--out OUT.json] [--log LOG.md]
Reads CSV, or XLSX when the path ends in .xlsx (needs openpyxl). Before any agreement is computed, a
coder file that is empty, equal to a comparison sheet on every shared coded cell, or equal to the other
coder's file is refused (exit 2); the match rate of each coder file against each comparison sheet is
printed either way.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

from make_sheets import LOCATION, VARS


def read(path: Path) -> list[dict]:
    if path.suffix == ".xlsx":
        from openpyxl import load_workbook
        ws = load_workbook(path, read_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        head = [str(h) for h in rows[0]]
        return [{h: ("" if v is None else str(v)).strip() for h, v in zip(head, r)} for r in rows[1:]]
    with path.open(encoding="utf-8") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if pe == 1:
        return None   # both coders used one value throughout: kappa is undefined
    return (po - pe) / (1 - pe)


def coded_cells(rows: dict, variables: list[str]) -> dict:
    return {(i, v): r[v] for i, r in rows.items() for v in variables if r.get(v)}


def check_sources(coders: dict, comparisons: dict, variables: list[str]) -> dict:
    """Refuse coder files that are not independent work: empty, a copy of a comparison sheet
    (every coded cell equal on the items both hold), or a copy of the other coder's file."""
    cells = {name: coded_cells(rows, variables) for name, rows in coders.items()}
    out = {"coded_cells": {n: len(c) for n, c in cells.items()}, "match_rate": {}, "refused": []}
    for name, c in cells.items():
        if not c:
            out["refused"].append(f"coder {name} file has no coded cells")
    for cname, crows in comparisons.items():
        ref = coded_cells(crows, variables)
        for name, c in cells.items():
            shared = [k for k in c if k in ref]
            same = sum(c[k] == ref[k] for k in shared)
            out["match_rate"][f"{name} vs {cname}"] = round(same / len(shared), 3) if shared else None
            if shared and same == len(shared):
                out["refused"].append(f"coder {name} file equals comparison sheet {cname} on all {len(shared)} shared cells")
    a, b = cells.get("A", {}), cells.get("B", {})
    shared = [k for k in a if k in b]
    if a and shared and len(shared) == len(a) == len(b) and all(a[k] == b[k] for k in shared):
        out["refused"].append("coder A and coder B files are identical")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", choices=["m1", "m2"], required=True)
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--log", type=Path)
    ap.add_argument("--comparison", type=Path, action="append", default=[],
                    help="a comparison sheet no coder file may be a copy of (repeatable)")
    ap.add_argument("--no-comparison-check", action="store_true",
                    help="run without any --comparison sheet (stated in the output)")
    x = ap.parse_args()
    if not x.comparison and not x.no_comparison_check:
        ap.error("give --comparison SHEET (or --no-comparison-check)")
    key = LOCATION[x.study][0]
    A = {r[key]: r for r in read(x.a)}
    B = {r[key]: r for r in read(x.b)}
    both = sorted(set(A) & set(B))
    variables = [f"coded_{v}" if v in LOCATION[x.study] else v for v in VARS[x.study]]
    guard = check_sources({"A": A, "B": B}, {str(p): {r[key]: r for r in read(p)} for p in x.comparison}, variables)
    print(json.dumps({"source_check": guard}, indent=1))
    if guard["refused"]:
        print("REFUSED: " + "; ".join(guard["refused"]))
        return 2
    rng = random.Random(20261008)
    result, disagreements = {"items_both": len(both), "variables": {}}, []
    for v in variables:
        pairs = [(A[i].get(v, ""), B[i].get(v, "")) for i in both if A[i].get(v) and B[i].get(v)]
        k = kappa(pairs)
        boots = []
        for _ in range(2000):
            s = [pairs[rng.randrange(len(pairs))] for _ in pairs] if pairs else []
            kb = kappa(s)
            if kb is not None:
                boots.append(kb)
        boots.sort()
        ci = (boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]) if len(boots) >= 100 else None
        result["variables"][v] = {"n": len(pairs), "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None,
                                  "kappa": None if k is None else round(k, 3),
                                  "ci95": None if ci is None else [round(ci[0], 3), round(ci[1], 3)],
                                  "below_0_6": k is not None and k < 0.6}
        for i in both:
            if A[i].get(v) and B[i].get(v) and A[i][v] != B[i][v]:
                disagreements.append({"item": i, "variable": v, "A": A[i][v], "B": B[i][v],
                                      "A_note": A[i].get("evidence_note", ""), "B_note": B[i].get("evidence_note", "")})
    result["disagreements"] = len(disagreements)
    print(json.dumps(result, indent=1))
    if x.out:
        x.out.write_text(json.dumps({**result, "disagreement_list": disagreements}, indent=1) + "\n", encoding="utf-8")
    if x.log:
        lines = [f"| {d['item']} | {d['variable']} | {d['A']} | {d['B']} | | |" for d in disagreements]
        with x.log.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
