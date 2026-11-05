#!/usr/bin/env python3
"""Real-chip control (T20): profiles and suites for a real e-passport read through a phone.

Committed (no personal data):
  profiles/real/VSC-pace-wrong-mrz.json        software chip, reader uses an MRZ with one digit changed
  profiles/real/REHEARSAL-pace-success.json    software chip behind the phone hub (relay mode)
  profiles/real/REHEARSAL-pace-wrong-mrz.json  same, wrong MRZ
  suites/real-rehearsal.json                   the three cells for every library entry of VSC-pace-success
Generated at run time only, never committed (profiles/real/local/ is gitignored):
  --real: profiles/real/local/REAL-pace-success.json and REAL-pace-wrong-mrz.json from the
  environment variable CBO_REAL_MRZ="DOCNUMBER:YYMMDD(birth):YYMMDD(expiry)"; the real-chip suite
  suites/real-chip.json refers to these paths.

The wrong MRZ changes the last character of the document number, so the reader derives a different
PACE (and BAC) key; the chip refuses PACE at its key check and BAC at EXTERNAL AUTHENTICATE.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELAY_PORT = 35964
VSC_MRZ = {"document_number": "T22000129", "date_of_birth": "640812", "date_of_expiry": "201031"}


def wrong(doc: str) -> str:
    last = doc[-1]
    if last.isdigit():
        return doc[:-1] + str((int(last) + 1) % 10)
    return doc[:-1] + ("B" if last != "B" else "C")


def profile(pid: str, name: str, mrz: dict, relay: bool, condition: str) -> dict:
    p = {"id": pid, "name": name, "mechanism": "PACE", "condition": condition, "tier": "independent",
         "mrz": mrz, "peer": "vsmartcard"}
    if relay:
        p["vsmartcard"] = {"relay": RELAY_PORT}
    return p


def write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def entries_for(test_case: str, profile_path: str, expect) -> list[dict]:
    base = json.loads((ROOT / "suites/independent.json").read_text())["entries"]
    out = []
    for e in base:
        if e["test_case"] != "VSC-pace-success":
            continue
        n = dict(e)
        n["scenario_id"] = e["scenario_id"].replace("VSC-pace-success", test_case)
        n["test_case"] = test_case
        n["cell"] = test_case
        n["profile"] = profile_path
        n.pop("expect_observation", None)
        n.pop("held_out", None)
        if expect is None:
            n.pop("expect_outcome", None)
        else:
            n["expect_outcome"] = expect
        out.append(n)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="write the real-chip profiles from CBO_REAL_MRZ")
    a = ap.parse_args()
    if a.real:
        doc, dob, doe = os.environ["CBO_REAL_MRZ"].split(":")
        mrz = {"document_number": doc, "date_of_birth": dob, "date_of_expiry": doe}
        bad = dict(mrz, document_number=wrong(doc))
        write(ROOT / "profiles/real/local/REAL-pace-success.json",
              profile("REAL-pace-success", "Real chip through the phone: correct MRZ", mrz, True, "pace_success"))
        write(ROOT / "profiles/real/local/REAL-pace-wrong-mrz.json",
              profile("REAL-pace-wrong-mrz", "Real chip through the phone: MRZ with one character changed",
                      bad, True, "pace_fail_wrong_key"))
        print("real-chip profiles written to profiles/real/local/ (gitignored)")
        return
    bad = dict(VSC_MRZ, document_number=wrong(VSC_MRZ["document_number"]))
    direct = profile("VSC-pace-wrong-mrz", "Independent chip: reader uses an MRZ with one character changed",
                     bad, False, "pace_fail_wrong_key")
    direct["vsmartcard"] = {"observe_refusals": True}  # the chip's own refusal is the delivered fault
    write(ROOT / "profiles/real/VSC-pace-wrong-mrz.json", direct)
    write(ROOT / "profiles/real/REHEARSAL-pace-success.json",
          profile("REHEARSAL-pace-success", "Independent chip behind the phone hub: correct MRZ",
                  VSC_MRZ, True, "pace_success"))
    write(ROOT / "profiles/real/REHEARSAL-pace-wrong-mrz.json",
          profile("REHEARSAL-pace-wrong-mrz", "Independent chip behind the phone hub: MRZ with one character changed",
                  bad, True, "pace_fail_wrong_key"))
    entries = (entries_for("VSC-pace-wrong-mrz", "profiles/real/VSC-pace-wrong-mrz.json", None)
               + entries_for("REHEARSAL-pace-success", "profiles/real/REHEARSAL-pace-success.json", "not_applicable")
               + entries_for("REHEARSAL-pace-wrong-mrz", "profiles/real/REHEARSAL-pace-wrong-mrz.json", None))
    write(ROOT / "suites/real-rehearsal.json", {
        "suite_id": "real-rehearsal",
        "description": ("T20 rehearsal: the software chip read directly with a wrong MRZ, and the software chip "
                        "behind the phone hub with the right and a wrong MRZ, for every library entry. The hub "
                        "path must give the same outcome as the direct path; the direct wrong-MRZ outcomes "
                        "become the real-chip expectations."),
        "seed": 1, "n": 1, "entries": entries})
    print(f"rehearsal: {len(entries)} entries")


if __name__ == "__main__":
    main()
