#!/usr/bin/env python3
"""Run the WebAuthn fault cases against one or more relying-party library drivers and classify.

For every (library, case) the driver prints its raw record (see webauthn/drivers/*). This runner
derives the five observations of the caller-boundary oracle from that record and the peer's
delivery report, then classifies them with the frozen oracle (classifier/observability.py,
unchanged; see classifier/ORACLE-FREEZE.md):

  fired           the delivery report names an injected fault and the driver passed exactly the
                  bytes the peer reported (SHA-256 match)
  returned_error  the verification call raised or returned an error
  status_signal   a field of the returned result reports the check that the fault violates as
                  failed (STATUS_FIELDS below; listed per library in webauthn/STATUS-SIGNALS.md)
  failed          returned_error or status_signal: the library recorded the failure
  succeeded       a field of the returned result reports that same check as passed

Results go to <out>/results.jsonl with the peer, driver and library provenance of each run, and are
compared with webauthn/expectations.json (committed before the runs) when --verify is given.

Usage: python3 webauthn/run.py --drivers webauthn/drivers.json --out logs/webauthn/<run-id> [--verify]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from classifier.observability import Observation, classify  # noqa: E402

# Per library: result fields that count as a status signal, the value that means "failed", and the
# faults whose check the field reports on. A field counts only if its value alone states that the
# property the violated step enforces did not hold (webauthn/STATUS-SIGNALS.md). Raw values that a
# caller would have to compare with something else (a new signature count against the stored one, a
# BS flag against a BE flag) do not count.
ALL_R = {"R-TYPE", "R-CHAL", "R-ORIG", "R-RPID", "R-UP", "R-UV", "R-BS", "R-ASIG"}
ALL_A = {"A-TYPE", "A-CHAL", "A-ORIG", "A-RPID", "A-UP", "A-UV", "A-BS", "A-SIG", "A-CNT"}
UV = {"R-UV", "A-UV"}
STATUS_FIELDS: dict[str, list[tuple[str, object, set[str]]]] = {
    "py_webauthn": [("user_verified", False, UV)],
    "simplewebauthn": [("verified", False, ALL_R | ALL_A), ("userVerified", False, UV)],
    "go-webauthn": [("user_verified", False, UV), ("clone_warning", True, {"A-CNT"})],
    "java-webauthn-server": [("success", False, ALL_A), ("signature_counter_valid", False, {"A-CNT"}),
                             ("user_verified", False, UV)],
    "webauthn4j-nonstrict": [("user_verified", False, UV)],
    "webauthn4j-strict": [("user_verified", False, UV)],
    "fido2-net-lib": [],
}


def run_driver(cmd: str, case_dir: Path) -> dict:
    p = subprocess.run(shlex.split(cmd) + [str(case_dir)], capture_output=True, text=True, timeout=300)
    lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if p.returncode != 0 or not lines:
        return {"driver_failed": True, "rc": p.returncode, "stderr": p.stderr[-500:]}
    return json.loads(lines[-1])


def observe(lib: str, report: dict, rec: dict) -> dict:
    fault = report["fault"]
    fired = bool(report["injected"]) and rec.get("passed_sha256") == report["response_sha256"]
    status = succeeded = False
    if not rec["returned_error"]:
        for field, bad, faults in STATUS_FIELDS[lib]:
            if fault in faults and field in rec["fields"]:
                if rec["fields"][field] == bad:
                    status = True
                else:
                    succeeded = True
    return {"fired": fired, "failed": rec["returned_error"] or status, "succeeded": succeeded and not status,
            "returned_error": rec["returned_error"], "status_signal": status}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drivers", default=str(ROOT / "webauthn" / "drivers.json"))
    ap.add_argument("--cases", default=None, help="existing case directory; default: generate into <out>/cases")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default=None, help="comma-separated library names")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = Path(a.cases) if a.cases else out / "cases"
    if not a.cases:
        subprocess.run([sys.executable, str(ROOT / "webauthn" / "authenticator.py"), "--out", str(cases)], check=True)
    vendor = os.environ.get("VENDOR_DIR", str(ROOT.parent / "_vendor"))
    drivers = {k: v.replace("{ROOT}", str(ROOT)).replace("{VENDOR}", vendor)
               for k, v in json.loads(Path(a.drivers).read_text(encoding="utf-8")).items()}
    only = set(a.only.split(",")) if a.only else None
    oracle_sha = hashlib.sha256((ROOT / "classifier" / "observability.py").read_bytes()).hexdigest()
    rows = []
    for lib, cmd in drivers.items():
        if only and lib not in only:
            continue
        for case_dir in sorted(p for p in cases.iterdir() if p.is_dir()):
            report = json.loads((case_dir / "report.json").read_text(encoding="utf-8"))
            rec = run_driver(cmd, case_dir)
            if rec.get("driver_failed"):
                row = {"library": lib, "case": report["case"], "outcome": "driver_failed", "record": rec}
            else:
                obs = observe(lib, report, rec)
                row = {"library": lib, "version": rec.get("version"), "case": report["case"], "fault": report["fault"],
                       "ceremony": report["ceremony"], "observations": obs,
                       "outcome": classify(Observation.from_dict(obs)).value,
                       "ceremony_accepted": not rec["returned_error"], "record": rec,
                       "peer_sha256": report["peer_sha256"], "oracle_sha256": oracle_sha}
            rows.append(row)
            print(f"{lib:16} {row['case']:12} {row['outcome']:15} {(row.get('record', {}).get('error_type') or '')}", flush=True)
    with (out / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    if a.verify:
        exp = json.loads((ROOT / "webauthn" / "expectations.json").read_text(encoding="utf-8"))
        bad = []
        for r in rows:
            e = exp.get(r["library"], {}).get(r["case"])
            if e is None or e["outcome"] != r["outcome"]:
                bad.append((r["library"], r["case"], e and e["outcome"], r["outcome"]))
            if r["case"].endswith("OK") or "-OK-" in r["case"]:
                if not r.get("ceremony_accepted"):
                    bad.append((r["library"], r["case"], "positive control accepted", "refused"))
        (out / "VERIFY.txt").write_text("\n".join(f"{l} {c}: expected {e}, got {g}" for l, c, e, g in bad) + "\n"
                                        if bad else "all outcomes as pre-registered\n", encoding="utf-8")
        print(f"verify: {len(bad)} mismatches")
        if bad:
            sys.exit(1)


if __name__ == "__main__":
    main()
