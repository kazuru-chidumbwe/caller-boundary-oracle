#!/usr/bin/env python3
"""Generate every synthetic chip profile the suites use.

Each profile targets one mechanism and injects one failure. Axes are limited to ones that
can change library behaviour: where the failure is injected and what kind of failure it is.
The MRZ is fixed (ICAO Doc 9303 Part 11 worked example), since it only changes key material.

  pace/         2 injection points x 16 failure kinds (13 status words, 3 channel faults) = 32
  ca/           Chip Authentication rejected at MSE:Set AT, 13 status words
  aa/           Active Authentication rejected at INTERNAL AUTHENTICATE, 13 status words
  controls/     no-injection and interoperability controls
  independent/  vsmartcard chip: PACE positive controls, PACE failed at MSE:Set AT and at each
                General Authenticate step (the ICAO status-word cases), AA rejected under SM

The status words are the union of the words the ICAO inspection-system conformity tests inject
(ICAO TR RF and Protocol Testing Part 4 V2.11: ISO7816_C_08, C_10, C_12, C_18, C_24, G_15) and
words outside them that exercise error-mapping code (6982, 6A88, 6FFF). Profiles that reproduce
an ICAO case carry its ID in "icao_p4"; ICAO has no status-word case for Active Authentication.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MRZ = {"document_number": "L898902C", "date_of_birth": "690806", "date_of_expiry": "940623"}
# PACEInfo: id-PACE-ECDH-GM-AES-CBC-CMAC-256, version 2, standardised parameter 13 (brainpoolP256r1).
CARD_ACCESS_PACE = "31143012060A04007F0007020204020402010202010D"
# Same PACEInfo with parameter 32: proprietary domain parameters, valid under Doc 9303 Part 11.
CARD_ACCESS_PROPRIETARY = "31143012060A04007F00070202040204020102020120"
STATUS_WORDS = ["6300", "6700", "6800", "6900", "6982", "6A00", "6A80", "6A88", "6B00", "6C00", "6E00", "6F00", "6FFF"]
CHANNEL_FAULTS = ["no_response", "timeout", "transport_abort"]
PACE_POINTS = ["mse_set_at", "general_authenticate"]

# ICAO TR RF and Protocol Testing Part 4 V2.11 status-word cases, by PACE step and status word.
ICAO_PACE = {
    "mse": {"6A80": "ISO7816_C_08a", "6A88": "ISO7816_C_08b", "6F00": "ISO7816_C_08c"},
    "ga1": {"6A80": "ISO7816_C_10a", "6F00": "ISO7816_C_10b"},
    "ga2": {"6A80": "ISO7816_C_12a", "6F00": "ISO7816_C_12b"},
    "ga3": {"6A80": "ISO7816_C_18a", "6F00": "ISO7816_C_18b"},
    "ga4": {"6300": "ISO7816_C_24a", "6A80": "ISO7816_C_24b", "6F00": "ISO7816_C_24c"},
}
# ISO7816_G_15: status word in response to Chip Authentication (injected here at MSE:Set AT).
ICAO_CA = {sw: f"ISO7816_G_15{c}" for sw, c in zip(
    ["6300", "6700", "6800", "6900", "6A00", "6B00", "6C00", "6E00", "6F00"], "abcdefghi")}
# The harness chip fails the first General Authenticate, which is PACE step 1.
HARNESS_PACE_STEP = {"mse_set_at": "mse", "general_authenticate": "ga1"}


def tag_icao(p: dict, case: str | None) -> None:
    if case:
        p["icao_p4"] = case


def base(pid: str, name: str, mechanism: str, condition: str) -> dict:
    return {"id": pid, "name": name, "mechanism": mechanism, "condition": condition, "tier": "wire", "mrz": dict(MRZ)}


def pace_profiles() -> dict[str, dict]:
    out = {}
    for point in PACE_POINTS:
        kinds = [("sw", sw) for sw in STATUS_WORDS] + [(ch, "") for ch in CHANNEL_FAULTS]
        for channel, sw in kinds:
            kind = sw.lower() if channel == "sw" else channel.replace("_", "-")
            pid = f"PACE-{point.replace('_', '-')}-{kind}"
            p = base(pid, f"PACE fails at {point} ({channel if channel != 'sw' else 'SW ' + sw})", "PACE", "pace_fail_then_bac")
            p["card_access_hex"] = CARD_ACCESS_PACE
            inj = {"pace_fail_on": point, "pace_sw": sw or "6FFF"}
            if channel != "sw":
                inj["pace_channel"] = channel
            p["injection"] = inj
            if channel == "sw":
                tag_icao(p, ICAO_PACE[HARNESS_PACE_STEP[point]].get(sw))
            out[f"pace/{pid}.json"] = p
    return out


def ca_profiles() -> dict[str, dict]:
    out = {}
    for sw in STATUS_WORDS:
        pid = f"CA-mse-set-at-{sw.lower()}"
        p = base(pid, f"Chip Authentication rejected at MSE:Set AT (SW {sw})", "CA", "ca_reject_after_bac")
        p["dg14_hex_path"] = "testdata/dg14/ca-v2-sample.hex"
        p["ca_injection"] = {"ca_fail_on": "mse_set_at", "ca_sw": sw}
        tag_icao(p, ICAO_CA.get(sw))
        out[f"ca/{pid}.json"] = p
    return out


def aa_profiles() -> dict[str, dict]:
    out = {}
    for sw in STATUS_WORDS:
        pid = f"AA-internal-authenticate-{sw.lower()}"
        p = base(pid, f"Active Authentication rejected at INTERNAL AUTHENTICATE (SW {sw})", "AA", "aa_reject_after_bac")
        p["dg15_hex_path"] = "testdata/dg15/aa-rsa-sample.hex"
        p["aa_injection"] = {"aa_fail_on": "internal_authenticate", "aa_sw": sw}
        out[f"aa/{pid}.json"] = p
    return out


def control_profiles() -> dict[str, dict]:
    bac_only = base("CTRL-bac-only", "No EF.CardAccess: PACE not advertised, BAC succeeds", "PACE", "pace_not_advertised")
    proprietary = base(
        "CTRL-pace-proprietary-params",
        "PACE advertised with proprietary domain parameters (ID 32); no failure injected on the wire",
        "PACE",
        "pace_unsupported_locally",
    )
    proprietary["card_access_hex"] = CARD_ACCESS_PROPRIETARY
    return {"controls/CTRL-bac-only.json": bac_only, "controls/CTRL-pace-proprietary-params.json": proprietary}


# MRZ data of the independent vsmartcard chip (tools/vsmartcard/emrtd_card.py).
VSC_MRZ = {"document_number": "T22000129", "date_of_birth": "640812", "date_of_expiry": "201031"}


def independent_profiles() -> dict[str, dict]:
    """Profiles for the vsmartcard chip: PACE and secure messaging by OpenPACE, not by the
    harness simulators. A PACE positive control, and AA rejected with each status word."""
    out = {}
    pace = base("VSC-pace-success", "Independent chip: PACE succeeds, EF.COM read over the PACE channel", "PACE", "pace_success")
    pace.update({"tier": "independent", "peer": "vsmartcard", "mrz": dict(VSC_MRZ)})
    out["independent/VSC-pace-success.json"] = pace
    multi = base("VSC-pace-success-multi-info",
                 "Independent chip: PACE succeeds; EF.CardAccess lists TA and CA infos before the PACEInfo (nPA layout)",
                 "PACE", "pace_success")
    multi.update({"tier": "independent", "peer": "vsmartcard", "mrz": dict(VSC_MRZ), "vsmartcard": {"card_access": "npa"}})
    out["independent/VSC-pace-success-multi-info.json"] = multi
    steps = {"mse": "MSE:Set AT", "ga1": "General Authenticate step 1", "ga2": "General Authenticate step 2",
             "ga3": "General Authenticate step 3", "ga4": "General Authenticate step 4"}
    for step, cases in ICAO_PACE.items():
        for sw, case in cases.items():
            pid = f"VSC-pace-{step}-{sw.lower()}"
            p = base(pid, f"Independent chip: PACE fails at {steps[step]} (SW {sw})", "PACE", "pace_fail_independent")
            p.update({"tier": "independent", "peer": "vsmartcard", "mrz": dict(VSC_MRZ),
                      "vsmartcard": {"pace_sw": sw, "pace_step": step}})
            tag_icao(p, case)
            out[f"independent/{pid}.json"] = p
    for sw in STATUS_WORDS:
        pid = f"VSC-aa-internal-authenticate-{sw.lower()}"
        p = base(pid, f"Independent chip: PACE, then INTERNAL AUTHENTICATE rejected with SW {sw} under SM", "AA", "aa_reject_after_pace")
        p.update({"tier": "independent", "peer": "vsmartcard", "mrz": dict(VSC_MRZ), "vsmartcard": {"dg15": True, "aa_sw": sw}})
        out[f"independent/{pid}.json"] = p
    return out


def main() -> None:
    profiles = {**pace_profiles(), **ca_profiles(), **aa_profiles(), **control_profiles(), **independent_profiles()}
    for sub in ("pace", "ca", "aa", "controls", "independent"):
        shutil.rmtree(ROOT / sub, ignore_errors=True)
    for rel, p in profiles.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(profiles)} profiles")


if __name__ == "__main__":
    main()
