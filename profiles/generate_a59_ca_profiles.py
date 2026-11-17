#!/usr/bin/env python3
"""A5-9: Chip Authentication on the independent chip, 13 status words, every CA arm.

So far Chip Authentication ran on the harness chip only (profiles/ca/: CA rejected at MSE:Set AT after BAC, 13 status
words), so the CA half of the D1 finding had no second peer. The independent chip (vsmartcard and OpenPACE,
tools/vsmartcard/emrtd_card.py) now serves DG14 (the harness chip's CA sample, testdata/dg14/ca-v2-sample.hex, listed
in EF.COM and in an SOD with its real hash, simulator/fixtures/vsc-sod-dg1-dg14.hex) and answers the first Chip
Authentication command (MSE:Set AT 41A4 or MSE:Set KAT 41A6) with the status word, under the PACE secure-messaging
channel (vsmartcard frames the error as it frames the AA rejection of the independent AA cells). Writes
profiles/a59ca/*.json and suites/a59-ca.json.

Each profile also carries the harness-chip "ca_injection" block (mse_set_at and the status word) as metadata: the
drivers take the recorded fault point from it; the independent chip ignores it.

Prediction (written here, before any run): every arm as on the harness chip, the same table and the same JMRTD rule
(suites/generate_suites.py EXPECT["CA"] and expect_for: catch-continue surfaced for 67xx words, where JMRTD's channel
loses step), since CA starts the same way on both chips and only the channel underneath differs (PACE here, BAC
there). gmrtd entries also allow not_applicable (INDEPENDENT_PACE_FLAKY: gmrtd fails PACE for real in about 1 in 256
sessions, before CA is reached). Arms without CA after access control (emrtd-dotnet, dmrtd, passauf) have no entries,
as on the harness chip.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("generate_suites", ROOT / "suites" / "generate_suites.py")
gs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gs)

STATUS_WORDS = ["6300", "6700", "6800", "6900", "6982", "6A00", "6A80", "6A88", "6B00", "6C00", "6E00", "6F00", "6FFF"]
VSC_MRZ = {"document_number": "T22000129", "date_of_birth": "640812", "date_of_expiry": "201031"}


def main() -> None:
    out = ROOT / "profiles" / "a59ca"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    entries = []
    for sw in STATUS_WORDS:
        pid = f"VSC-ca-mse-set-at-{sw.lower()}"
        p = {"id": pid, "name": f"Independent chip: PACE, then Chip Authentication rejected at MSE:Set AT (SW {sw}) under SM",
             "mechanism": "CA", "condition": "ca_reject_after_pace", "tier": "independent", "peer": "vsmartcard",
             "mrz": dict(VSC_MRZ), "vsmartcard": {"dg14": True, "ca_sw": sw},
             "ca_injection": {"ca_fail_on": "mse_set_at", "ca_sw": sw}}
        rel = f"profiles/a59ca/{pid}.json"
        (ROOT / rel).write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8", newline="\n")
        expect = gs.expect_for(p, "CA")
        for e in gs.entries_for(rel, p, "VSC-CA", expect):
            if e["library"] in gs.INDEPENDENT_PACE_FLAKY:
                e["expect_outcome"] = [e["expect_outcome"], gs.NA]
            entries.append(e)
    suite = {"suite_id": "a59-ca", "seed": 1, "n": 1,
             "description": ("A5-9: Chip Authentication rejected at MSE:Set AT on the independent chip, 13 status words, "
                             "every CA arm; predictions as on the harness chip (profiles/generate_a59_ca_profiles.py), "
                             "committed before the run."),
             "entries": entries}
    (ROOT / "suites/a59-ca.json").write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(STATUS_WORDS)} profiles, {len(entries)} entries")


if __name__ == "__main__":
    main()
