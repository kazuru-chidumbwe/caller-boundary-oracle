#!/usr/bin/env python3
"""U6: PACE step 4 answered 9000 with a changed body, on the independent chip, for JMRTD 0.8.9.

The chip runs the real step 4 (it checks the reader's token and switches to the PACE session
keys) and then answers 9000 with one of four bodies (tools/vsmartcard/emrtd_card.py, ga4_body).
Writes profiles/u6/*.json and suites/u6-jmrtd.json. Expectations are written here, from the
JMRTD 0.8.9 source, before any run.

Source path (jmrtd-sources-0.8.9, scuba-smartcards 0.0.21 as shaded in the driver jar):
  PACEAPDUSender.sendGeneralAuthenticate: SW 9000, then TLVUtil.unwrapDO(0x7C, data).
  PACEProtocol.doPACEStep4: reads tag 86, length, value from the unwrapped bytes inside
  try { ... } catch (IOException ioe) { LOGGER.log(WARNING, "Could not parse step 4 response") };
  after the catch it returns null, the same value a GM or IM step 4 returns on success, and
  doPACE then builds the PACE result with the new secure-messaging wrapper. The token
  comparison (expected T_PICC vs received) only runs if the parse got that far. Any other
  exception in step 4 becomes CardServiceProtocolException (step 4), which doPACE throws.

Parse outcome of each body against that code and scuba 0.0.21 (checked with a probe of the
same calls on Testbed A, 5 Nov 2026):
  empty-7c      7C00                    unwrapDO -> empty; readTag -> EOFException -> null
  truncated-86  7C04 8608 xxxx          unwrapDO -> 8608xxxx; readValue -> EOFException -> null
  wrong-token   7C0A 8608 <~T_PICC>     parsed; token mismatch -> GeneralSecurityException -> thrown
  no-data       (none)                  unwrapDO -> IllegalArgumentException -> thrown

Driver (drivers/jmrtd JmrtdRead.readWithPace): doPACE, then SELECT, then BAC only if PACE did not
complete, then EF.COM. "fired" is the chip's delivered-fault report for PACE.

Expectations:
  empty-7c, truncated-86, both integrators: doPACE returns normally (the chip's token is never
    checked), the session keys are the right ones because the chip did complete step 4, EF.COM
    reads over PACE secure messaging. succeeded, no error, no status: silent. The failure is
    only in JMRTD's log.
  wrong-token, no-data, propagate: doPACE throws (step 4), the read routine passes it on:
    surfaced.
  wrong-token, no-data, catch-continue: the integrator swallows the PACE exception and tries BAC.
    The chip completed PACE step 4, so its EAC state is past PACE and the card's EXTERNAL
    AUTHENTICATE goes to Terminal Authentication instead of BAC (emrtd_card.install_bac); BAC
    fails, the read routine returns an error: surfaced. (On the step-4 status-word cells the
    chip never finished step 4 and BAC succeeds, hence silent there.)
  VSC-pace-success, both integrators: not_applicable, succeeded (positive control in the same run).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MRZ = {"document_number": "T22000129", "date_of_birth": "640812", "date_of_expiry": "201031"}

BODIES = {
    "empty-7c": ("7C00, no authentication token", "silent", "silent"),
    "truncated-86": ("7C04 86 08 and two token bytes, token cut short", "silent", "silent"),
    "wrong-token": ("full-length token with every bit inverted", "surfaced", "surfaced"),
    "no-data": ("no response data", "surfaced", "surfaced"),
}


def main() -> None:
    out = ROOT / "profiles" / "u6"
    out.mkdir(exist_ok=True)
    entries = []
    for body, (desc, exp_prop, exp_cc) in BODIES.items():
        pid = f"VSC-pace-ga4body-{body}"
        profile = {
            "id": pid,
            "name": f"Independent chip: PACE step 4 completed by the chip, answered 9000 with {desc}",
            "mechanism": "PACE",
            "condition": "pace_fail_independent",
            "tier": "independent",
            "mrz": MRZ,
            "peer": "vsmartcard",
            "vsmartcard": {"ga4_body": body},
        }
        path = out / f"{pid}.json"
        path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        for integrator, exp in (("propagate", exp_prop), ("catch-continue", exp_cc)):
            entries.append({
                "scenario_id": f"{pid}-jmrtd-{integrator}",
                "test_case": pid,
                "library": "jmrtd",
                "variant": integrator,
                "cell": "VSC-PACE-GA4BODY",
                "driver": "java",
                "integrator": integrator,
                "profile": f"profiles/u6/{pid}.json",
                "expect_outcome": exp,
            })
    for integrator in ("propagate", "catch-continue"):
        entries.append({
            "scenario_id": f"VSC-pace-success-jmrtd-{integrator}",
            "test_case": "VSC-pace-success",
            "library": "jmrtd",
            "variant": integrator,
            "cell": "VSC-pace-success",
            "driver": "java",
            "integrator": integrator,
            "profile": "profiles/independent/VSC-pace-success.json",
            "expect_outcome": "not_applicable",
            "expect_observation": {"succeeded": True, "returned_error": False},
        })
    suite = {
        "suite_id": "u6-jmrtd",
        "description": ("U6: JMRTD 0.8.9, PACE step 4 completed by the independent chip and answered 9000 "
                        "with a changed body (empty 7C, truncated 86, wrong token, no data), both "
                        "integrators, with the PACE positive control. Expectations from the 0.8.9 source "
                        "(profiles/generate_u6_profiles.py), committed before the run."),
        "seed": 1,
        "n": 1,
        "entries": entries,
    }
    (ROOT / "suites" / "u6-jmrtd.json").write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    print(f"{len(BODIES)} profiles, {len(entries)} entries")


if __name__ == "__main__":
    main()
