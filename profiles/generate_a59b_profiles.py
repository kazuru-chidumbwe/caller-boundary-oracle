#!/usr/bin/env python3
"""A5-9b: every PACE failure kind on the independent chip at General Authenticate steps 2 to 4.

The harness chip fails PACE at two points (MSE:Set AT and the first General Authenticate) with 16 failure kinds:
the 13 status words of profiles/generate_profiles.py and its 3 channel faults (no_response, timeout,
transport_abort: an empty frame, the timeout after 50 ms). The independent chip (vsmartcard and OpenPACE,
tools/vsmartcard/emrtd_card.py) so far ran only the ICAO TR Part 4 cases: 12 status-word cells over MSE:Set AT and
the four General Authenticate steps, 7 of them at steps 2 to 4. This adds the other 41 cells at steps 2 to 4 (the
steps only the independent chip can fail, since it runs PACE for real): the 13 status words minus the ICAO ones at
each step, and the 3 channel faults (emrtd_card.py pace_channel). Writes profiles/a59b/*.json and
suites/a59b-pace-steps.json.

Prediction (written here, before any run): every entry expects what the same library arm does on the existing
independent cell at the same step (VSC-pace-<step>-6a80, which suites/independent.json predicts as the harness
chip's PACE table), since no reader in the study branches on which status word or which empty answer ends PACE:
each treats any non-9000 answer, and any answer too short to carry a status word, as a PACE failure and goes on
as it does after 6A80 (falls back to BAC, or stops). gmrtd and dmrtd keep not_applicable as an allowed outcome
(INDEPENDENT_PACE_FLAKY: they fail PACE for real in a few per cent of sessions before the targeted step).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_WORDS = ["6300", "6700", "6800", "6900", "6982", "6A00", "6A80", "6A88", "6B00", "6C00", "6E00", "6F00", "6FFF"]
CHANNEL_FAULTS = ["no_response", "timeout", "transport_abort"]
ICAO = {"ga2": {"6A80", "6F00"}, "ga3": {"6A80", "6F00"}, "ga4": {"6300", "6A80", "6F00"}}
STEP_NAME = {"ga2": "General Authenticate step 2", "ga3": "General Authenticate step 3", "ga4": "General Authenticate step 4"}


def main() -> None:
    out = ROOT / "profiles" / "a59b"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    independent = json.loads((ROOT / "suites/independent.json").read_text(encoding="utf-8"))["entries"]
    entries, n_prof = [], 0
    for step in ("ga2", "ga3", "ga4"):
        ref_case = f"VSC-pace-{step}-6a80"
        ref_prof = json.loads((ROOT / "profiles/independent" / f"{ref_case}.json").read_text(encoding="utf-8"))
        base = [e for e in independent if e["test_case"] == ref_case]
        assert base, ref_case
        kinds = [("sw", sw) for sw in STATUS_WORDS if sw not in ICAO[step]] + [(ch, "") for ch in CHANNEL_FAULTS]
        for channel, sw in kinds:
            kind = sw.lower() if channel == "sw" else channel.replace("_", "-")
            pid = f"VSC-pace-{step}-{kind}"
            what = f"SW {sw}" if channel == "sw" else channel
            vs = {"pace_step": step, "pace_sw": sw or "6FFF"}
            if channel != "sw":
                vs["pace_channel"] = channel
            p = {k: v for k, v in ref_prof.items() if k not in ("icao_p4",)}
            p.update({"id": pid, "name": f"Independent chip: PACE fails at {STEP_NAME[step]} ({what})", "vsmartcard": vs})
            (out / f"{pid}.json").write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8", newline="\n")
            n_prof += 1
            for e in base:
                n = {k: v for k, v in e.items() if k not in ("held_out", "icao_p4")}
                n["scenario_id"] = e["scenario_id"].replace(ref_case, pid)
                n["test_case"] = pid
                n["profile"] = f"profiles/a59b/{pid}.json"
                entries.append(n)
    suite = {"suite_id": "a59b-pace-steps", "seed": 1, "n": 1,
             "description": ("A5-9b: the 41 PACE failure kinds the independent chip had not run at General Authenticate "
                             "steps 2 to 4 (status words and channel faults); predictions from the 6A80 cell at the same "
                             "step (profiles/generate_a59b_profiles.py), committed before the run."),
             "entries": entries}
    (ROOT / "suites/a59b-pace-steps.json").write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {n_prof} profiles, {len(entries)} entries")


if __name__ == "__main__":
    main()
