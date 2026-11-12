#!/usr/bin/env python3
"""U7b: U7 on two chips, one that serves LDS files after a failed BAC and one that enforces access control.

U7 used the independent chip as vsmartcard ships it: after EXTERNAL AUTHENTICATE failed, it still served EF.SOD,
EF.COM and DG1 in plain. A genuine chip refuses plain access to LDS files with 6982 (Doc 9303 Part 11), so U7b
runs every library entry on both chips, at one commit: "serving" (vsmartcard as shipped, the behaviour of a clone
or an emulator) and "enforcing" (tools/vsmartcard/emrtd_card.py access_control "enforce"). Both chips have no
EF.CardAccess, so every reader uses BAC. Wrong MRZ = document number T22000120 instead of T22000129; the chip's own
refusal of EXTERNAL AUTHENTICATE is the delivered fault (observe_refusals "PACE", the access-control key the drivers
read). Writes profiles/u7b/*.json and suites/u7b-bac.json. Expectations are written here, before any run.

Right MRZ, both chips: positive control, not_applicable (the read succeeds; every reader uses secure messaging
after BAC, so the enforcing chip serves it).

Wrong MRZ, serving chip (as U7):
  gmrtd, every pin, default and opt-in fallback: performBac records the BAC error in Session.BacErr and returns nil
    ("NB errors are just recorded at this point"; reader.go at 8fea245, 64bd6ab, b861835), then readEfDir, readEfSod,
    readEfCom and readLDS1dgs read in plain and get the files: ReadDocument returns no error and the failure is only
    in the session: status_only.
  gmrtd + guard: surfaced (the guard turns BacErr into an error).
  JMRTD (both integrators), dmrtd, emrtd-dotnet, passauf: their BAC call throws or returns the error: surfaced.

Wrong MRZ, enforcing chip:
  gmrtd, every pin, default and opt-in fallback: performBac records BacErr and returns nil as above. readEfDir sends
    a plain SELECT of EF.DIR (2F00) inside the eMRTD application; the chip has no such file there and answers
    6A82, which SelectEF treats as file not found (nil error). readEfSod then sends a plain SELECT of EF.SOD (011D,
    P1 02); the enforcing chip answers 6982, SelectEF returns "Invalid status:6982", ReadFile and readEfSod wrap it,
    and ReadDocument returns the error: surfaced (at a later step than BAC, with an error that names the file read,
    not the access-control failure).
  gmrtd + guard: surfaced (ReadDocument already returns the error; the guard also sees BacErr).
  JMRTD, dmrtd, emrtd-dotnet, passauf: unchanged, they stop at BAC: surfaced.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MRZ = {"document_number": "T22000129", "date_of_birth": "640812", "date_of_expiry": "201031"}
WRONG = dict(MRZ, document_number="T22000120")
CHIPS = {
    "serving": ("an independent chip that serves LDS files in plain after a failed BAC (vsmartcard as shipped)", {}),
    "enforcing": ("an independent chip that refuses plain access to LDS files (6982), as a genuine chip does",
                  {"access_control": "enforce"}),
}


def expect_wrong(e: dict, chip: str) -> str:
    if e["library"] == "gmrtd" and not e["variant"].endswith("guard"):
        return "status_only" if chip == "serving" else "surfaced"
    return "surfaced"


def main() -> None:
    out = ROOT / "profiles" / "u7b"
    out.mkdir(exist_ok=True)
    cells = {}
    for chip, (desc, extra) in CHIPS.items():
        cells[f"VSC-bac-only-{chip}-success"] = (
            f"BAC with the right MRZ on {desc}", MRZ, "bac_only_success", chip, dict({"card_access": "none"}, **extra))
        cells[f"VSC-bac-only-{chip}-wrong-mrz"] = (
            f"BAC with an MRZ with one character changed on {desc}", WRONG, "bac_only_wrong_key", chip,
            dict({"card_access": "none", "observe_refusals": "PACE"}, **extra))
    for pid, (name, mrz, cond, _chip, vs) in cells.items():
        p = {"id": pid, "name": name, "mechanism": "PACE", "condition": cond, "tier": "independent",
             "mrz": mrz, "peer": "vsmartcard", "vsmartcard": vs}
        (out / f"{pid}.json").write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8")
    base = [e for e in json.loads((ROOT / "suites/independent.json").read_text())["entries"]
            if e["test_case"] == "VSC-pace-success"]
    entries = []
    for pid, (_name, _mrz, _cond, chip, _vs) in cells.items():
        for e in base:
            n = {k: v for k, v in e.items() if k not in ("expect_observation", "held_out")}
            n["scenario_id"] = e["scenario_id"].replace("VSC-pace-success", pid)
            n["test_case"] = pid
            n["cell"] = pid
            n["profile"] = f"profiles/u7b/{pid}.json"
            n["expect_outcome"] = "not_applicable" if pid.endswith("success") else expect_wrong(e, chip)
            entries.append(n)
    suite = {"suite_id": "u7b-bac",
             "description": ("U7b: U7 on a chip that serves LDS files after a failed BAC and on a chip that enforces "
                             "access control, right and wrong MRZ, every library entry. Expectations from source "
                             "(profiles/generate_u7b_profiles.py), committed before the run."),
             "seed": 1, "n": 1, "entries": entries}
    (ROOT / "suites/u7b-bac.json").write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    print(f"{len(entries)} entries")


if __name__ == "__main__":
    main()
