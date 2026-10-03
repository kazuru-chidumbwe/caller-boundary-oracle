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
SINGLE_ARMS = {"emrtd-dotnet": ("emrtd-dotnet", "dotnet"), "dmrtd": ("dmrtd", "dart")}

# Expected outcome per mechanism and arm. None means the arm does not apply to the mechanism.
EXPECT = {
    "PACE": {
        "8fea245-default": ST, "64bd6ab-default": SU, "64bd6ab-allow-fallback": ST,
        "8fea245-guard": SU, "64bd6ab-guard": SU, "propagate": SU, "catch-continue": S,
        # falls back to BAC; the returned document names the access control actually used
        "emrtd-dotnet": ST,
        # the caller chooses PACE or BAC up front; a PACE failure throws
        "dmrtd": SU,
    },
    "CA": {
        "8fea245-default": ST, "64bd6ab-default": ST, "64bd6ab-allow-fallback": None,
        "8fea245-guard": SU, "64bd6ab-guard": SU, "propagate": None, "catch-continue": None,
        "emrtd-dotnet": None, "dmrtd": None,
    },
    "AA": {
        "8fea245-default": ST, "64bd6ab-default": ST, "64bd6ab-allow-fallback": None,
        "8fea245-guard": SU, "64bd6ab-guard": SU, "propagate": SU, "catch-continue": S,
        "emrtd-dotnet": None, "dmrtd": SU,
    },
}
# JMRTD 0.8.9 AAAPDUSender.sendInternalAuthenticate returns the response data for any status
# word once a response object exists (an empty array counts), so doAA returns normally and no
# integrator pattern sees the failure. With the harness simulator, which answers errors in
# plaintext, a response object only survives for status words matching (sw & 0x6700) == 0x6700
# (secure messaging skips them as "wrong length"): 6F00 and 6FFF. With the independent chip,
# which answers errors under secure messaging, it survives for every status word.
JMRTD_AA_SWALLOWED = {"6F00", "6FFF"}

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
    if mechanism == "AA" and prof["aa_injection"]["aa_sw"] in JMRTD_AA_SWALLOWED:
        expect["propagate"] = S
        expect["catch-continue"] = S
    return expect


def load_profiles(sub: str) -> list[tuple[str, dict]]:
    return [
        (f"profiles/{sub}/{p.name}", json.loads(p.read_text(encoding="utf-8")))
        for p in sorted((ROOT / "profiles" / sub).glob("*.json"))
    ]


INDEPENDENT_EXPECT = {
    "PACE": {arm: NA for arm in EXPECT["PACE"]},
    "AA": {
        "8fea245-default": ST, "64bd6ab-default": ST, "64bd6ab-allow-fallback": None,
        "8fea245-guard": SU, "64bd6ab-guard": SU, "propagate": S, "catch-continue": S,
        "emrtd-dotnet": None, "dmrtd": SU,
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
        want = dict(observation or {})
        if returned_error:
            want["returned_error"] = returned_error[e.get("arm", e["variant"])]
        if want:
            e["expect_observation"] = want
    return out


def write(suite_id: str, description: str, entries: list[dict]) -> None:
    doc = {"suite_id": suite_id, "description": description, "seed": 1, "n": 1, "entries": entries}
    path = ROOT / "suites" / f"{suite_id}.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote suites/{suite_id}.json ({len(entries)} runs)")


def main() -> None:
    pace = [e for rel, p in load_profiles("pace") for e in entries_for(rel, p, "PACE", EXPECT["PACE"])]
    write("pace", "PACE failure injected at two points, eight failure kinds; gmrtd at both pins, guard, opt-in; JMRTD integrator patterns.", pace)

    ca_aa = [e for rel, p in load_profiles("ca") for e in entries_for(rel, p, "CA", expect_for(p, "CA"))]
    ca_aa += [e for rel, p in load_profiles("aa") for e in entries_for(rel, p, "AA", expect_for(p, "AA"))]
    write("ca-aa", "Chip and Active Authentication rejected after BAC; gmrtd at both pins with and without guard; JMRTD AA integrator patterns.", ca_aa)

    controls = [
        e
        for rel, p in load_profiles("controls")
        for e in entries_for(rel, p, p["id"], CONTROL_EXPECT[p["id"]], CONTROL_RETURNED_ERROR[p["id"]])
    ]
    write("controls", "No-injection control (BAC-only chip) and interoperability control (proprietary PACE domain parameters).", controls)

    independent = []
    for rel, p in load_profiles("independent"):
        if p["mechanism"] == "PACE":
            # Positive controls: nothing is injected, so every arm is not applicable. JMRTD and
            # emrtd-dotnet must also complete PACE and the read; gmrtd and dmrtd may fail PACE
            # intermittently (see INDEPENDENT_PACE_FLAKY).
            entries = entries_for(rel, p, p["id"], INDEPENDENT_EXPECT["PACE"])
            multi = p.get("vsmartcard", {}).get("card_access") == "npa"
            for e in entries:
                if multi and e["library"] == "dmrtd":
                    # dmrtd reads only the first SecurityInfo, misses PACE and is refused BAC
                    e["expect_observation"] = {"succeeded": False, "returned_error": True}
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
    repeat_arms = {"8fea245-default", "64bd6ab-default", "b861835-default", "propagate", "emrtd-dotnet", "dmrtd"}
    repeat = []
    for rel, p in load_profiles("independent"):
        if p["id"] != "VSC-pace-success":
            continue
        for e in entries_for(rel, p, "VSC-PACE-REPEAT", INDEPENDENT_EXPECT["PACE"]):
            if e.get("arm", e["variant"]) in repeat_arms:
                e["n"] = REPEAT_N
                repeat.append(e)
    write("independent-repeat", f"PACE positive control on the independent chip, {REPEAT_N} runs per library.", repeat)

    smoke_profile = "profiles/pace/PACE-mse-set-at-6fff.json"
    smoke = [e for e in pace if e["profile"] == smoke_profile]
    write("smoke", "One PACE profile across every arm.", smoke)


if __name__ == "__main__":
    main()
