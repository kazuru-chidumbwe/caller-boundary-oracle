#!/usr/bin/env python3
"""Write the suite manifests from profiles/ and the arm definitions below.

An arm is one library build plus one caller choice. Every profile in a suite runs once per
arm (the chip simulators are deterministic, so repeating a run adds nothing). Each entry
carries the outcome the oracle is expected to report; verify_manifest.py fails the run if
any differs.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S, ST, SU, NA = "silent", "status_only", "surfaced", "not_applicable"
REPEAT_N = 100

# gmrtd arms: (variant, pin, allow_bac_fallback, guard)
GMRTD_ARMS = {
    "8fea245-default": ("8fea245", False, False),
    "64bd6ab-default": ("64bd6ab", False, False),
    "64bd6ab-allow-fallback": ("64bd6ab", True, False),
    "8fea245-guard": ("8fea245", False, True),
    "64bd6ab-guard": ("64bd6ab", False, True),
    "b861835-default": ("b861835", False, False),
    "b861835-allow-fallback": ("b861835", True, False),
    "b861835-guard": ("b861835", False, True),
}
JMRTD_ARMS = ("propagate", "catch-continue")
# Libraries with a single caller path, driven through cmd/chip-serve: arm name -> (library, driver)
SINGLE_ARMS = {"emrtd-dotnet": ("emrtd-dotnet", "dotnet"), "dmrtd": ("dmrtd", "dart"), "passauf": ("passauf", "rust")}

# Expected outcome per mechanism and arm. None means the arm does not apply to the mechanism.
EXPECT = {
    "PACE": {
        "8fea245-default": ST, "64bd6ab-default": SU, "64bd6ab-allow-fallback": ST,
        "8fea245-guard": SU, "64bd6ab-guard": SU, "propagate": SU, "catch-continue": S,
        # falls back to BAC; the returned document names the access control actually used
        "emrtd-dotnet": ST,
        # the caller chooses PACE or BAC up front; a PACE failure throws
        "dmrtd": SU,
        # passauf v0.2.0 (48b7cc7), held out (expectations written from source before its first run):
        # session.rs read_document logs warn!(error) and falls back to BAC on any PACE error
        # (select_pace_info or do_pace_authentication, lines 426 to 445, 503 to 535); the returned
        # DocumentRead names the authentication used (Authentication::Bac), the only record of it
        "passauf": ST,
    },
    "CA": {
        # opt-in arm: the BAC-fallback flag changes PACE only; CA and AA stay status-only as in the default arm,
        # as the version sweep measured for every release that has the flag (analysis/out/VERSION-SWEEP.md, T15)
        "8fea245-default": ST, "64bd6ab-default": ST, "64bd6ab-allow-fallback": ST,
        "8fea245-guard": SU, "64bd6ab-guard": SU, "propagate": SU, "catch-continue": S,
        "emrtd-dotnet": None, "dmrtd": None,
        # passauf has Chip Authentication only as PACE-CAM, no MSE:Set KAT/AT CA after BAC
        "passauf": None,
    },
    "AA": {
        "8fea245-default": ST, "64bd6ab-default": ST, "64bd6ab-allow-fallback": ST,
        "8fea245-guard": SU, "64bd6ab-guard": SU, "propagate": SU, "catch-continue": S,
        "emrtd-dotnet": None, "dmrtd": SU,
        # passauf implements no Active Authentication (no INTERNAL AUTHENTICATE in the sources)
        "passauf": None,
    },
}
# JMRTD 0.8.9 AAAPDUSender.sendInternalAuthenticate returns the response data for any status
# word once a response object exists (an empty array counts), so doAA returns normally and no
# integrator pattern sees the failure. Both chips answer an error to INTERNAL AUTHENTICATE as a
# protected response (Doc 9303 Part 11 §9.8.3 and §9.8.5: only secure-messaging errors are
# answered in plain), so the response object survives for every status word. (An earlier Java
# in-process chip answered these errors in plain; there only (sw & 0x6700) == 0x6700 survived.)
def _jmrtd_aa_swallowed(sw: str) -> bool:
    return True


# JMRTD 0.8.9 EACCAAPDUSender.sendMSESetATIntAuth throws CardServiceException for any status
# word other than 9000, so doEACCA throws: propagate is surfaced for every status word, and
# catch-and-continue goes on to read EF.COM over the existing secure channel. That read succeeds
# (silent) unless the error desynchronised the channel: SecureMessagingAPDUSender.transmit returns
# a response whose status word matches (sw & 0x6700) == 0x6700 without unwrapping it, so the
# reader's send sequence counter falls one behind the chip's, the chip rejects the MAC of the next
# command, and the EF.COM read throws (surfaced, through the later read rather than the CA step).
def _jmrtd_ca_desyncs(sw: str) -> bool:
    return (int(sw, 16) & 0x6700) == 0x6700

CONTROL_EXPECT = {
    "CTRL-bac-only": {arm: NA for arm in EXPECT["PACE"]},
    "CTRL-pace-proprietary-params": {arm: NA for arm in EXPECT["PACE"]},
}
# Nothing is injected in the controls; returned_error shows which arms refuse the read anyway.
CONTROL_RETURNED_ERROR = {
    "CTRL-bac-only": {arm: False for arm in EXPECT["PACE"]},
    "CTRL-pace-proprietary-params": {
        "8fea245-default": False, "64bd6ab-default": True, "64bd6ab-allow-fallback": False,
        "8fea245-guard": True, "64bd6ab-guard": True, "propagate": True, "catch-continue": False,
        "emrtd-dotnet": False, "dmrtd": True,
        # passauf: a proprietary parameter ID is rejected by pace::select_pace_info ("reserved for
        # future use", mod.rs lines 308 to 316), so read_document falls back to BAC without an error
        "passauf": False,
    },
}



def _add_v132(table: dict) -> None:
    """v1.3.2 behaves as v1.1.3 in every arm measured here; expectations are copied, and the
    runs check that this holds."""
    for row in table.values():
        for suffix in ("default", "allow-fallback", "guard"):
            if f"64bd6ab-{suffix}" in row:
                row[f"b861835-{suffix}"] = row[f"64bd6ab-{suffix}"]



def expect_for(prof: dict, mechanism: str) -> dict[str, str | None]:
    expect = dict(EXPECT[mechanism])
    if mechanism == "AA" and _jmrtd_aa_swallowed(prof["aa_injection"]["aa_sw"]):
        expect["propagate"] = S
        expect["catch-continue"] = S
    if mechanism == "CA" and _jmrtd_ca_desyncs(prof["ca_injection"]["ca_sw"]):
        expect["catch-continue"] = SU
    return expect


def load_profiles(sub: str) -> list[tuple[str, dict]]:
    return [
        (f"profiles/{sub}/{p.name}", json.loads(p.read_text(encoding="utf-8")))
        for p in sorted((ROOT / "profiles" / sub).glob("*.json"))
    ]


INDEPENDENT_EXPECT = {
    "PACE": {arm: NA for arm in EXPECT["PACE"]},
    "AA": {
        "8fea245-default": ST, "64bd6ab-default": ST, "64bd6ab-allow-fallback": ST,
        "8fea245-guard": SU, "64bd6ab-guard": SU, "propagate": S, "catch-continue": S,
        "emrtd-dotnet": None, "dmrtd": SU, "passauf": None,
    },
}
# On the independent chip (random ephemeral keys) gmrtd and dmrtd occasionally fail PACE
# for real: gmrtd does not pad the ECDH shared secret (about 1 in 256 runs), dmrtd does not pad
# EC coordinates (a few per cent). When that happens the targeted step is never reached and the
# run is not applicable; their entries allow it, and suites/independent-repeat.json measures
# the rates. JMRTD and emrtd-dotnet completed PACE in every run and stay pinned exactly.
INDEPENDENT_PACE_FLAKY = {"gmrtd", "dmrtd"}


for _table in (EXPECT, CONTROL_EXPECT, CONTROL_RETURNED_ERROR, INDEPENDENT_EXPECT):
    _add_v132(_table)

# PACE failed by the independent chip: predicted as on the harness chip, measured below.
INDEPENDENT_PACE_FAULT = dict(EXPECT["PACE"])


def entries_for(
    rel: str,
    prof: dict,
    cell: str,
    expect: dict[str, str | None],
    returned_error: dict[str, bool] | None = None,
    observation: dict[str, bool] | None = None,
) -> list[dict]:
    out = []
    for arm, (pin, fallback, guard) in GMRTD_ARMS.items():
        if expect.get(arm) is None:
            continue
        out.append({
            "scenario_id": f"{prof['id']}-gmrtd-{arm}",
            "test_case": prof["id"],
            "library": "gmrtd",
            "variant": arm,
            "cell": cell,
            "driver": "go",
            "command": "gmrtd-read",
            "gmrtd_pin": pin,
            "allow_bac_fallback": fallback,
            "guard": guard,
            "profile": rel,
            "expect_outcome": expect[arm],
        })
    for arm in JMRTD_ARMS:
        if expect.get(arm) is None:
            continue
        out.append({
            "scenario_id": f"{prof['id']}-jmrtd-{arm}",
            "test_case": prof["id"],
            "library": "jmrtd",
            "variant": arm,
            "cell": cell,
            "driver": "java",
            "integrator": arm,
            "profile": rel,
            "expect_outcome": expect[arm],
        })
    for arm, (library, driver) in SINGLE_ARMS.items():
        if expect.get(arm) is None:
            continue
        out.append({
            "scenario_id": f"{prof['id']}-{library}-default",
            "test_case": prof["id"],
            "library": library,
            "variant": "default",
            "arm": arm,
            "cell": cell,
            "driver": driver,
            "profile": rel,
            "expect_outcome": expect[arm],
        })
    for e in out:
        if prof.get("icao_p4"):
            e["icao_p4"] = prof["icao_p4"]
        want = dict(observation or {})
        if returned_error:
            want["returned_error"] = returned_error[e.get("arm", e["variant"])]
        if want:
            e["expect_observation"] = want
    return out


# NFCPassportReader (iOS): one arm, run by .github/workflows/ios.yml in the iOS Simulator.
# TagReader.send treats a response as an error only when sw1 != 0x90 AND sw2 != 0x00 (upstream
# PR #272), so every status word with SW2 = 00 reaches the caller as a success response. For PACE
# and CA the step is still recorded as failed; Active Authentication then fails verification
# without an error (status-only) instead of throwing (surfaced).
def ios_expect(prof: dict) -> str:
    mechanism = prof["mechanism"]
    if prof["id"].startswith("CTRL-") or prof.get("condition") == "pace_success":
        return NA
    if mechanism == "AA":
        sw = prof.get("aa_injection", {}).get("aa_sw") or prof.get("vsmartcard", {}).get("aa_sw")
        return ST if sw.endswith("00") else SU
    return ST  # PACE falls back to BAC; CA is recorded in chipAuthenticationStatus


def ios_cell(p: dict) -> str:
    """Same cells as the Linux suites: controls and positive controls are their own cell."""
    if p["id"].startswith("CTRL-") or p.get("condition") == "pace_success":
        return p["id"]
    return ("VSC-" if p.get("peer") == "vsmartcard" else "") + p["mechanism"]


def ios_entries() -> list[dict]:
    out = []
    for sub in ("pace", "ca", "aa", "controls", "independent"):
        for rel, p in load_profiles(sub):
            e = {
                "scenario_id": f"{p['id']}-nfcpassportreader-default",
                "test_case": p["id"],
                "library": "nfcpassportreader",
                "variant": "default",
                "cell": ios_cell(p),
                "driver": "ios",
                "profile": rel,
                "expect_outcome": ios_expect(p),
            }
            if p.get("icao_p4"):
                e["icao_p4"] = p["icao_p4"]
            if p.get("condition") == "pace_success" and p.get("vsmartcard", {}).get("card_access") != "npa":
                e["expect_observation"] = {"succeeded": True, "returned_error": False}
            out.append(e)
    return out


# Libraries held out from the development of the oracle and harness: their expectations were committed before
# their first run (af4a92d for passauf) and are predictions; a mismatch is a result, reported by verify_manifest.py,
# not a harness fault.
HELD_OUT = {"passauf"}


def write(suite_id: str, description: str, entries: list[dict]) -> None:
    for e in entries:
        if e.get("library") in HELD_OUT:
            e["held_out"] = True
    doc = {"suite_id": suite_id, "description": description, "seed": 1, "n": 1, "entries": entries}
    path = ROOT / "suites" / f"{suite_id}.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote suites/{suite_id}.json ({len(entries)} runs)")


def main() -> None:
    pace = [e for rel, p in load_profiles("pace") for e in entries_for(rel, p, "PACE", EXPECT["PACE"])]
    write("pace", "PACE failure injected at two points, eight failure kinds; gmrtd at both pins, guard, opt-in; JMRTD integrator patterns.", pace)

    ca_aa = [e for rel, p in load_profiles("ca") for e in entries_for(rel, p, "CA", expect_for(p, "CA"))]
    ca_aa += [e for rel, p in load_profiles("aa") for e in entries_for(rel, p, "AA", expect_for(p, "AA"))]
    write("ca-aa", "Chip and Active Authentication rejected after BAC; gmrtd at three pins with and without guard; JMRTD integrator patterns.", ca_aa)

    controls = [
        e
        for rel, p in load_profiles("controls")
        for e in entries_for(rel, p, p["id"], CONTROL_EXPECT[p["id"]], CONTROL_RETURNED_ERROR[p["id"]])
    ]
    write("controls", "No-injection control (BAC-only chip) and interoperability control (proprietary PACE domain parameters).", controls)

    independent = []
    for rel, p in load_profiles("independent"):
        if p["mechanism"] == "PACE" and p.get("vsmartcard", {}).get("pace_step"):
            # PACE failed by the independent chip at one step. The chip offers no BAC, so arms
            # that fall back after the failure cannot finish the read; see INDEPENDENT_PACE_FAULT.
            entries = entries_for(rel, p, "VSC-PACE", INDEPENDENT_PACE_FAULT)
            for e in entries:
                if e["library"] in INDEPENDENT_PACE_FLAKY:
                    e["expect_outcome"] = [e["expect_outcome"], NA]
            independent += entries
        elif p["mechanism"] == "PACE":
            # Positive controls: nothing is injected, so every arm is not applicable. JMRTD and
            # emrtd-dotnet must also complete PACE and the read; gmrtd and dmrtd may fail PACE
            # intermittently (see INDEPENDENT_PACE_FLAKY).
            entries = entries_for(rel, p, p["id"], INDEPENDENT_EXPECT["PACE"])
            multi = p.get("vsmartcard", {}).get("card_access") == "npa"
            for e in entries:
                if multi and e["library"] == "dmrtd":
                    # dmrtd reads only the first SecurityInfo, misses PACE and reads over BAC
                    # without telling the caller that the chip offered PACE (a silent downgrade)
                    e["expect_observation"] = {"succeeded": False, "returned_error": False}
                elif e["library"] not in INDEPENDENT_PACE_FLAKY:
                    e["expect_observation"] = {"succeeded": True, "returned_error": False}
            independent += entries
        else:
            entries = entries_for(rel, p, "VSC-AA", INDEPENDENT_EXPECT["AA"])
            for e in entries:
                if e["library"] in INDEPENDENT_PACE_FLAKY:
                    e["expect_outcome"] = [e["expect_outcome"], NA]
            independent += entries
    write("independent", "Independent vsmartcard/OpenPACE chip: PACE positive control; AA rejected under secure messaging.", independent)

    # PACE positive control repeated per library: the behaviour classes count how often each
    # library fails PACE against the independent chip.
    repeat_arms = {"8fea245-default", "64bd6ab-default", "b861835-default", "propagate", "emrtd-dotnet", "dmrtd", "passauf"}
    repeat = []
    for rel, p in load_profiles("independent"):
        if p["id"] != "VSC-pace-success":
            continue
        for e in entries_for(rel, p, "VSC-PACE-REPEAT", INDEPENDENT_EXPECT["PACE"]):
            if e.get("arm", e["variant"]) in repeat_arms:
                e["n"] = REPEAT_N
                repeat.append(e)
    write("independent-repeat", f"PACE positive control on the independent chip, {REPEAT_N} runs per library.", repeat)

    write("ios", "NFCPassportReader in the iOS Simulator: every harness and independent-chip profile (.github/workflows/ios.yml).",
          ios_entries())

    smoke_profile = "profiles/pace/PACE-mse-set-at-6fff.json"
    smoke = [e for e in pace if e["profile"] == smoke_profile]
    write("smoke", "One PACE profile across every arm.", smoke)


if __name__ == "__main__":
    main()
