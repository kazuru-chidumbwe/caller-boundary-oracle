#!/usr/bin/env python3
"""Coding sheets for M1 and M2 (PROTOCOL.md: sampling and coding; CODEBOOK.md v1.1: variables and values).

Coder A codes every item; coder B codes a random 30 per cent, drawn with random.Random(20261008) over the
sorted item IDs. For M2, a library with more than 40 eligible call sites is first reduced to 40, drawn with
random.Random(20261004) over its sorted call-site IDs (PROTOCOL.md, sampling). Location columns are filled
in; the variable columns, evidence_note, uncertain and uncertainty_note are empty. Each sheet is written as
CSV (the record) and as XLSX with a drop-down list per variable (for the coder).

Usage: python mining/make_sheets.py --study m1|m2 --items ITEMS.csv --out DIR [--batch 1]
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

VARS = {
    "m1": {
        "step": ["PACE", "BAC", "CA", "AA", "TA", "SM", "FILE", "PA", "OTHER", "NOT_A_SITE"],
        "channel": ["THROW", "RETURN", "STATUS", "CONVERT", "LOG", "SWALLOW"],
        "continues": ["YES", "NO"],
        "fallback": ["BAC", "RETRY", "OTHER", "NONE"],
        "reaches_api": ["DIRECT", "INDIRECT", "NO"],
    },
    "m2": {
        "library": ["gmrtd", "JMRTD", "emrtd-dotnet", "dmrtd", "NFCPassportReader", "passauf", "OTHER"],
        "step": ["PACE", "CA", "AA", "READ"],
        "handling": ["PROPAGATE", "CHECK", "LOG_CONTINUE", "IGNORE", "NA"],
        "user_visible_accept": ["YES", "NO", "UNCLEAR"],
        "misuse_class": ["MISSING_CALL", "REDUNDANT_CALL", "MISSING_NULL_CHECK", "REDUNDANT_NULL_CHECK",
                         "MISSING_VALUE_OR_STATE", "REDUNDANT_VALUE_OR_STATE", "MISSING_SYNC", "REDUNDANT_SYNC",
                         "MISSING_CONTEXT", "REDUNDANT_CONTEXT", "MISSING_ITERATION", "REDUNDANT_ITERATION",
                         "MISSING_EXCEPTION_HANDLING", "REDUNDANT_EXCEPTION_HANDLING", "NONE"],
        "lineage": [],   # free text: ORIGINAL, FORK_OF(repo), COPIED_FROM(repo)
    },
}
LOCATION = {
    "m1": ["site_id", "library", "versions", "file", "line", "function", "kinds", "step_hint", "code", "context"],
    "m2": ["callsite_id", "library", "repo", "step", "commit", "file", "line", "code", "url"],
}
TAIL = ["evidence_note", "uncertain", "uncertainty_note"]


def write(rows: list[dict], study: str, path: Path) -> None:
    variables = list(VARS[study])
    # M2 already carries library and step as location columns; the coder confirms them as variables
    var_cols = [f"coded_{v}" if v in LOCATION[study] else v for v in variables]
    fields = LOCATION[study] + var_cols + TAIL
    with path.with_suffix(".csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    try:
        from openpyxl import Workbook
        from openpyxl.worksheet.datavalidation import DataValidation
    except ImportError:
        return
    wb = Workbook()
    ws = wb.active
    ws.title = study.upper()
    ws.append(fields)
    for r in rows:
        ws.append([r.get(c, "") for c in fields])
    n = len(rows) + 1
    for col, (v, values) in enumerate(zip(var_cols, VARS[study].values()), start=len(LOCATION[study]) + 1):
        if not values:
            continue
        dv = DataValidation(type="list", formula1='"' + ",".join(values) + '"', allow_blank=True)
        letter = ws.cell(row=1, column=col).column_letter
        dv.add(f"{letter}2:{letter}{n}")
        ws.add_data_validation(dv)
    unc = len(LOCATION[study]) + len(var_cols) + 2
    dv = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
    letter = ws.cell(row=1, column=unc).column_letter
    dv.add(f"{letter}2:{letter}{n}")
    ws.add_data_validation(dv)
    ws.freeze_panes = ws.cell(row=2, column=len(LOCATION[study]) + 1)
    wb.save(path.with_suffix(".xlsx"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", choices=["m1", "m2"], required=True)
    ap.add_argument("--items", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--batch", default="1")
    a = ap.parse_args()
    key = LOCATION[a.study][0]
    with a.items.open(encoding="utf-8") as f:
        items = sorted(csv.DictReader(f), key=lambda r: r[key])
    note = []
    if a.study == "m2":
        by_lib = defaultdict(list)
        for r in items:
            by_lib[r["library"]].append(r)
        kept = []
        for lib in sorted(by_lib):
            rows = sorted(by_lib[lib], key=lambda r: r[key])
            if len(rows) > 40:
                rows = sorted(random.Random(20261004).sample(rows, 40), key=lambda r: r[key])
                note.append(f"{lib}: 40 of {len(by_lib[lib])} drawn")
            else:
                note.append(f"{lib}: all {len(rows)}")
            kept += rows
        items = sorted(kept, key=lambda r: r[key])
    ids = [r[key] for r in items]
    b_ids = set(random.Random(20261008).sample(ids, round(0.3 * len(ids))))
    a.out.mkdir(parents=True, exist_ok=True)
    write(items, a.study, a.out / f"batch{a.batch}-{a.study}-coder-A")
    write([r for r in items if r[key] in b_ids], a.study, a.out / f"batch{a.batch}-{a.study}-coder-B")
    print(f"{a.study}: coder A {len(items)} items, coder B {len(b_ids)} items; " + "; ".join(note))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
