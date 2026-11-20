#!/usr/bin/env python3
"""Write the run plan for the NFCPassportReader driver (drivers/ios) from suites/ios.json: one
entry per manifest entry, with the MRZ key NFCPassportReader expects (document number padded
to 9 characters, date of birth, date of expiry, each followed by its check digit)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_digit(s: str) -> str:
    weights = (7, 3, 1)
    total = 0
    for i, c in enumerate(s):
        v = 0 if c == "<" else int(c) if c.isdigit() else ord(c) - 55
        total += v * weights[i % 3]
    return str(total % 10)


def mrz_key(mrz: dict) -> str:
    doc = mrz["document_number"].ljust(9, "<")
    dob, doe = mrz["date_of_birth"], mrz["date_of_expiry"]
    return doc + check_digit(doc) + dob + check_digit(dob) + doe + check_digit(doe)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, default=ROOT / "suites" / "ios.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--skip-independent", action="store_true", help="leave out vsmartcard profiles")
    args = ap.parse_args()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    plan = []
    for e in json.loads(args.manifest.read_text(encoding="utf-8"))["entries"]:
        p = json.loads((ROOT / e["profile"]).read_text(encoding="utf-8"))
        if args.skip_independent and p.get("peer") == "vsmartcard":
            continue
        plan.append({
            "run_id": f"{e['scenario_id']}-{stamp}-{len(plan) + 1:06d}",
            "scenario_id": e["scenario_id"],
            "profile": e["profile"],
            "mechanism": p["mechanism"],
            "mrz_key": mrz_key(p["mrz"]),
            # nfcpr-optin: the driver sets allowChipAuthenticationFailure and
            # allowActiveAuthenticationFailure to false for this run.
            "optin": bool(e.get("optin", False)),
        })
    args.out.write_text(json.dumps(plan, indent=2) + chr(10), encoding="utf-8")
    print(f"wrote {len(plan)} runs to {args.out}")


if __name__ == "__main__":
    main()
