#!/usr/bin/env python3
"""Turn the NFCPassportReader test output into run artifacts.

Reads the "CBO-RESULT <json>" lines printed by drivers/ios (library-side observations), the
plan, and the broker's <run_id>.chip.json reports (whether the chip delivered the fault), and
writes one run artifact per run in the common schema, classified with the shared oracle.

NFCPassportReader reports each step in the returned NFCPassportModel: PACEStatus and
chipAuthenticationStatus (notDone / success / failed) and activeAuthenticationPassed. A step
recorded as failed there, with the read returning normally, is a status signal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "classifier"))
from observability import Observation, classify  # noqa: E402

MEANING = {
    "silent": "silent: call succeeded, failure not reachable by the caller",
    "status_only": "status-only: call succeeded, failure recorded in a returned status field",
    "surfaced": "surfaced: error returned or thrown to the caller",
    "not_applicable": "not applicable: injected failure did not fire",
    "invalid": "invalid: library reported the step as both failed and successful",
}


def git(cwd: Path, *args: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def step_state(mechanism: str, r: dict) -> tuple[bool, bool]:
    if mechanism == "PACE":
        return r.get("pace_status") == "failed", r.get("pace_status") == "success"
    if mechanism == "CA":
        return r.get("chip_authentication_status") == "failed", r.get("chip_authentication_status") == "success"
    if mechanism == "AA":
        supported, passed = r.get("active_authentication_supported", False), r.get("active_authentication_passed", False)
        return supported and not passed, passed
    return False, False


def fault_point(profile: dict, mechanism: str) -> str:
    if profile.get("peer") == "vsmartcard":
        vs = profile.get("vsmartcard", {})
        if mechanism == "AA":
            return "AA/internal_authenticate" if vs.get("aa_sw") else ""
        step = vs.get("pace_step", "")
        if not step:
            return ""
        return "PACE/mse_set_at" if step == "mse" else f"PACE/general_authenticate_step{step[2:]}"
    if mechanism == "PACE":
        fail_on = profile.get("injection", {}).get("pace_fail_on")
        return f"PACE/{fail_on}" if profile.get("card_access_hex") and fail_on else ""
    if mechanism == "CA":
        return "CA/" + profile.get("ca_injection", {}).get("ca_fail_on", "")
    if mechanism == "AA":
        return "AA/" + profile.get("aa_injection", {}).get("aa_fail_on", "")
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--test-log", type=Path, required=True)
    ap.add_argument("--chip-reports", type=Path, required=True)
    ap.add_argument("--log-dir", type=Path, required=True)
    ap.add_argument("--suite-id", default="ios")
    args = ap.parse_args()

    results = {}
    for line in args.test_log.read_text(encoding="utf-8", errors="replace").splitlines():
        idx = line.find("CBO-RESULT ")
        if idx >= 0:
            r = json.loads(line[idx + len("CBO-RESULT "):])
            results[r["run_id"]] = r

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    commit = git(ROOT, "rev-parse", "HEAD") or "unknown"
    dirty = bool(git(ROOT, "status", "--porcelain", "--untracked-files=no"))
    lib_commit = git(ROOT.parent / "_vendor" / "NFCPassportReader", "rev-parse", "HEAD")
    xcode = (subprocess.run(["xcodebuild", "-version"], capture_output=True, text=True).stdout.split("\n")[0]
             if sys.platform == "darwin" else None)
    args.log_dir.mkdir(parents=True, exist_ok=True)
    missing = 0
    for i, entry in enumerate(plan, start=1):
        r = results.get(entry["run_id"])
        if r is None or "harness_error" in r:
            missing += 1
            print(f"no result for {entry['run_id']}: {r.get('harness_error') if r else 'missing'}", file=sys.stderr)
            continue
        profile_path = ROOT / entry["profile"]
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        mechanism = entry["mechanism"]
        report_path = args.chip_reports / f"{entry['run_id']}.chip.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        fired = bool(report.get("fault_delivered", {}).get(mechanism))
        failed, succeeded = step_state(mechanism, r)
        obs = Observation(fired, failed, succeeded, bool(r.get("read_err")), failed)
        outcome = classify(obs)
        artifact = {
            "run_id": entry["run_id"],
            "scenario_id": entry["scenario_id"],
            "test_case": profile["id"],
            "library": "nfcpassportreader",
            "mechanism": mechanism,
            "condition": profile.get("condition"),
            "tier": profile.get("tier", "wire"),
            "variant": "optin" if entry.get("optin") else "default",
            "provenance": {
                "harness_commit": commit,
                "harness_dirty": dirty,
                "nfcpassportreader_commit": lib_commit,
                "xcode_version": xcode,
                "profile_path": entry["profile"],
                "profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                "suite_id": args.suite_id,
                "suite_seed": 1,
                "suite_n": 1,
                "run_index": i,
                "driver": "ios/NFCPassportReaderOracleTests",
                "variant": "optin" if entry.get("optin") else "default",
                "caller_options": {"allowChipAuthenticationFailure": False, "allowActiveAuthenticationFailure": False} if entry.get("optin") else None,
                "captured_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "outcome": outcome.value,
            "observability_score": outcome.score,
            "observability_meaning": MEANING[outcome.value],
            "observation": {
                "fired": obs.fired, "failed": obs.failed, "succeeded": obs.succeeded,
                "returned_error": obs.returned_error, "status_signal": obs.status_signal,
            },
            "fault_point": fault_point(profile, mechanism),
            "pace_status": r.get("pace_status"),
            "chip_authentication_status": r.get("chip_authentication_status"),
            "active_authentication_passed": r.get("active_authentication_passed"),
            "read_err": r.get("read_err", ""),
            "trace": r.get("trace", []),
        }
        (args.log_dir / f"{entry['run_id']}.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        print(f"{profile['id']} nfcpassportreader: {outcome.value}")
    if missing:
        raise SystemExit(f"{missing} run(s) without a result")


if __name__ == "__main__":
    main()
