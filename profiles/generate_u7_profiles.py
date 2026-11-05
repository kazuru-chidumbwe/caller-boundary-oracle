#!/usr/bin/env python3
"""U7: access control on a chip without PACE (BAC only), with the right and a wrong MRZ, every library entry.

The independent chip serves no EF.CardAccess (card_access "none"), so every reader uses BAC. With a wrong MRZ
the chip refuses EXTERNAL AUTHENTICATE; observe_refusals records that refusal as the delivered fault under
"PACE", the key the drivers read for the access-control step. Writes profiles/u7/*.json and suites/u7-bac.json.
Expectations are written here, before any run.

Expectations for the wrong MRZ (the right MRZ is a positive control: not_applicable, read succeeds):
  gmrtd, every pin, default and opt-in fallback: performBac records the BAC error in Session.BacErr and
    returns nil ("NB errors are just recorded at this point"; reader.go at 8fea245, 64bd6ab, b861835, and
    unchanged in v1.4.0, v1.7.1 and v1.8.0); no PACE error exists to fail closed on, so ReadDocument returns
    no error and the failure is only in the session: status_only (with the access-control mapping of ledger B.10).
  gmrtd + guard: the guard checks the access-control error (PaceErr, else BacErr; ledger B.10): surfaced.
  JMRTD, both integrators: no EF.CardAccess, so the read routine calls doBAC, which throws; the integrator
    patterns catch only PACE, so the BAC exception leaves the read routine: surfaced.
  dmrtd: no PACEInfo, so the driver calls Passport.startSession (BAC), which throws on failure: surfaced.
  emrtd-dotnet and passauf: both fall back to BAC after a PACE failure and surfaced when that BAC failed
    (T20 rehearsal at 805261a, wrong MRZ on a PACE chip); the same BAC path runs here: surfaced.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MRZ = {"document_number": "T22000129", "date_of_birth": "640812", "date_of_expiry": "201031"}
WRONG = dict(MRZ, document_number="T22000120")


def expect_wrong(e: dict) -> str:
    if e["library"] == "gmrtd":
        return "surfaced" if e["variant"].endswith("guard") else "status_only"
    return "surfaced"


def main() -> None:
    out = ROOT / "profiles" / "u7"
    out.mkdir(exist_ok=True)
    cells = {
        "VSC-bac-only-success": ("Independent chip without PACE: BAC with the right MRZ", MRZ, "bac_only_success",
                                 {"card_access": "none"}),
        "VSC-bac-only-wrong-mrz": ("Independent chip without PACE: BAC with an MRZ with one character changed",
                                   WRONG, "bac_only_wrong_key", {"card_access": "none", "observe_refusals": "PACE"}),
    }
    for pid, (name, mrz, cond, vs) in cells.items():
        p = {"id": pid, "name": name, "mechanism": "PACE", "condition": cond, "tier": "independent",
             "mrz": mrz, "peer": "vsmartcard", "vsmartcard": vs}
        (out / f"{pid}.json").write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8")
    base = [e for e in json.loads((ROOT / "suites/independent.json").read_text())["entries"]
            if e["test_case"] == "VSC-pace-success"]
    entries = []
    for pid in cells:
        for e in base:
            n = {k: v for k, v in e.items() if k not in ("expect_observation", "held_out")}
            n["scenario_id"] = e["scenario_id"].replace("VSC-pace-success", pid)
            n["test_case"] = pid
            n["cell"] = pid
            n["profile"] = f"profiles/u7/{pid}.json"
            n["expect_outcome"] = "not_applicable" if pid.endswith("success") else expect_wrong(e)
            entries.append(n)
    suite = {"suite_id": "u7-bac",
             "description": ("U7: a chip without PACE read over BAC with the right and a wrong MRZ, every library "
                             "entry. Expectations from source (profiles/generate_u7_profiles.py), committed before "
                             "the run."),
             "seed": 1, "n": 1, "entries": entries}
    (ROOT / "suites/u7-bac.json").write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    print(f"{len(entries)} entries")


if __name__ == "__main__":
    main()
