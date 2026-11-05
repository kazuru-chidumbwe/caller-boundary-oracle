#!/usr/bin/env python3
"""Consequence demo: run the JMRTD SampleReader on the runs in expectations.json and check each result.

From the harness root:  python3 examples/t13-consequence/run.py
Builds the JMRTD driver jar and cmd/chip-serve if missing; writes examples/t13-consequence/out/<ts>/.
Exit 0 only if every run matches its expectation.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
JAR = ROOT / "drivers/jmrtd/target/jmrtd-driver-0.1.0.jar"
CHIP = ROOT / "bin/chip-serve"


def build() -> None:
    if not JAR.is_file():
        subprocess.check_call(["bash", str(ROOT / "scripts/install-jmrtd-local.sh")], cwd=ROOT)
        subprocess.check_call(["mvn", "-q", "-DskipTests", "package"], cwd=ROOT / "drivers/jmrtd")
    if not CHIP.is_file():
        subprocess.check_call(["go", "build", "-o", str(CHIP), "./cmd/chip-serve"], cwd=ROOT)


def main() -> int:
    build()
    spec = json.loads((HERE / "expectations.json").read_text())
    out = HERE / "out" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out.mkdir(parents=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    rows, ok = [], True
    for run in spec["runs"]:
        res_path = out / f"{run['id']}.json"
        p = subprocess.run(["java", "-cp", str(JAR), "org.callerboundary.jmrtd.SampleReader",
                            "-profile", str(ROOT / run["profile"]), "-chip-serve", str(CHIP),
                            "-mode", run["mode"], "-out", str(res_path)],
                           cwd=ROOT, capture_output=True, text=True, timeout=300)
        if not res_path.is_file():
            rows.append({"id": run["id"], "held": False, "runner_fault": p.stderr[-500:]})
            ok = False
            continue
        res = json.loads(res_path.read_text())
        got = {k: res.get(k) for k in run["expect"]}
        held = got == run["expect"]
        ok &= held
        rows.append({"id": run["id"], "mode": run["mode"], "profile": run["profile"], "expect": run["expect"],
                     "got": got, "held": held, "display": res.get("display"), "error": res.get("error")})
        print(f"{run['id']} {'held' if held else 'NOT HELD'}: {res.get('display')}", flush=True)
    (out / "SUMMARY.json").write_text(json.dumps({"harness_commit": commit, "all_held": ok, "runs": rows}, indent=1) + "\n")
    print(f"{'ALL HELD' if ok else 'NOT ALL HELD'} ({out})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
