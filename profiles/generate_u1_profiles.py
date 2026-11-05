#!/usr/bin/env python3
"""Profiles for U1 (gmrtd RequireAuthenticDocument) that the existing suites do not have.

They run only on the trusted-chain chip (gmrtd-read -trusted-chain); see
generate_trusted_fixtures.py. The single-method CA and AA failure cells reuse the existing
profiles in profiles/ca and profiles/aa unchanged.

  U1-AA-ok, U1-CA-ok            positive controls: the method succeeds (E2, E5)
  U1-DUAL-AA-<sw>               DG14 and DG15, AA fails with <sw>, CA succeeds (E9)
  U1-DUAL-CA-<sw>               DG14 and DG15, CA fails with <sw>, AA succeeds (E10)
  U1-DUAL-ok                    DG14 and DG15, both succeed (E11)
  U1-DUAL-BOTH-<sw>             DG14 and DG15, both fail with <sw> (E12)

Status words are the thirteen of the existing AA and CA cells.
Usage: python profiles/generate_u1_profiles.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "profiles" / "u1"
SWS = ["6300", "6700", "6800", "6900", "6982", "6a00", "6a80", "6a88", "6b00", "6c00", "6e00", "6f00", "6fff"]
MRZ = {"document_number": "L898902C", "date_of_birth": "690806", "date_of_expiry": "940623"}
DG14 = "testdata/dg14/ca-v2-sample.hex"  # selects DG14; the trusted chip serves its own DG14
DG15 = "testdata/dg15/aa-rsa-sample.hex"  # selects DG15; the trusted chip serves its own DG15


def write(p: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{p['id']}.json").write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8")


def base(pid: str, name: str, mech: str, cond: str) -> dict:
    return {"id": pid, "name": name, "mechanism": mech, "condition": cond, "tier": "wire", "mrz": MRZ}


def main() -> None:
    p = base("U1-AA-ok", "Trusted chip, Active Authentication succeeds", "AA", "aa_ok_trusted")
    p["dg15_hex_path"] = DG15
    write(p)
    p = base("U1-CA-ok", "Trusted chip, Chip Authentication succeeds", "CA", "ca_ok_trusted")
    p["dg14_hex_path"] = DG14
    write(p)
    p = base("U1-DUAL-ok", "Trusted chip with DG14 and DG15, both methods succeed", "AA", "dual_ok_trusted")
    p["dual"] = True
    write(p)
    for sw in SWS:
        p = base(f"U1-DUAL-AA-{sw}", f"Trusted chip with DG14 and DG15, AA rejected (SW {sw.upper()}), CA succeeds",
                 "AA", "dual_aa_reject_ca_ok")
        p.update(dual=True, aa_injection={"aa_fail_on": "internal_authenticate", "aa_sw": sw.upper()})
        write(p)
        p = base(f"U1-DUAL-CA-{sw}", f"Trusted chip with DG14 and DG15, CA rejected at MSE:Set AT (SW {sw.upper()}), AA succeeds",
                 "CA", "dual_ca_reject_aa_ok")
        p.update(dual=True, ca_injection={"ca_fail_on": "mse_set_at", "ca_sw": sw.upper()})
        write(p)
        p = base(f"U1-DUAL-BOTH-{sw}", f"Trusted chip with DG14 and DG15, AA and CA both rejected (SW {sw.upper()})",
                 "AA", "dual_both_reject")
        p.update(dual=True, aa_injection={"aa_fail_on": "internal_authenticate", "aa_sw": sw.upper()},
                 ca_injection={"ca_fail_on": "mse_set_at", "ca_sw": sw.upper()})
        write(p)
    print(f"wrote {len(list(OUT.glob('*.json')))} profiles to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
