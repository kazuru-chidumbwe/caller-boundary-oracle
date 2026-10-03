#!/usr/bin/env python3
"""Write the run plan for the NFCPassportReader driver (drivers/ios): one entry per profile,
with the MRZ key NFCPassportReader expects (document number padded to 9 characters, date of
birth, date of expiry, each followed by its check digit)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRS = ("pace", "ca", "aa", "controls")


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
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dirs", nargs="*", default=list(DEFAULT_DIRS))
    args = ap.parse_args()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    plan = []
    for sub in args.dirs:
        for path in sorted((ROOT / "profiles" / sub).glob("*.json")):
            p = json.loads(path.read_text(encoding="utf-8"))
            plan.append({
                "run_id": f"{p['id']}-nfcpassportreader-default-{stamp}-{len(plan) + 1:06d}",
                "profile": path.relative_to(ROOT).as_posix(),
                "mechanism": p["mechanism"],
                "mrz_key": mrz_key(p["mrz"]),
            })
    args.out.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(plan)} runs to {args.out}")


if __name__ == "__main__":
    main()
