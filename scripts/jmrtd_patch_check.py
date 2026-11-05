#!/usr/bin/env python3
"""Run JMRTD suite entries unpatched and with a proposed upstream patch, to back an upstream report.

The patch is applied to the vendored JMRTD 0.8.9 source (../_vendor/jmrtd-sources-0.8.9), the changed
classes are compiled against the driver jar and placed before it on the classpath (the mutation
harness's method). Every JMRTD entry of the given manifests runs twice, unpatched and patched.
Writes analysis/data/jmrtd-patch-<set>-<ts>/SUMMARY.json and patch.diff.

Usage (from the harness root, vsmartcard.env sourced for independent-chip entries):
  python3 scripts/jmrtd_patch_check.py --set pace-step4 suites/u6-jmrtd.json suites/independent.json suites/pace.json
"""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / "drivers/jmrtd/target/jmrtd-driver-0.1.0.jar"
VSRC = ROOT.parent / "_vendor/jmrtd-sources-0.8.9"
CHIP = ROOT / "bin/chip-serve"

PATCH_SETS = {
    # SourceForge bug #90: doAA returns normally when the chip rejects INTERNAL AUTHENTICATE.
    "aa-status": [
        ("AAAPDUSender.java",
         "responseAPDU != null && responseAPDU.getData() != null) {",
         "responseAPDU != null && responseAPDU.getData() != null && responseAPDU.getData().length > 0) {"),
        ("SecureMessagingAPDUSender.java",
         "(sw & ISO7816.SW_WRONG_LENGTH) == ISO7816.SW_WRONG_LENGTH",
         "(sw & 0xFF00) == ISO7816.SW_WRONG_LENGTH"),
    ],
    # PACE step 4: a step-4 response that cannot be parsed ends PACE instead of returning null
    # (the success value for Generic and Integrated Mapping). doPACEStep4's outer catch wraps the
    # GeneralSecurityException as CardServiceProtocolException, step 4, as for a token mismatch.
    "pace-step4": [
        ("PACEProtocol.java",
         'LOGGER.log(Level.WARNING, "Could not parse step 4 response", ioe);',
         'throw new GeneralSecurityException("Could not parse step 4 response", ioe);'),
    ],
}


def find_src(name: str) -> Path:
    hits = glob.glob(str(VSRC / "**" / name), recursive=True)
    assert len(hits) == 1, f"{name}: {len(hits)} source files found: {hits}"
    return Path(hits[0])


def prepare(edits, work: Path, classes: Path, out: Path) -> None:
    for d in (work, classes):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    patched, diff = [], []
    for name, old, new in edits:
        src = find_src(name)
        text = src.read_text(encoding="utf-8")
        assert text.count(old) == 1, f"{name}: anchor appears {text.count(old)}x, not 1: {old!r}"
        changed = text.replace(old, new)
        rel = src.relative_to(VSRC)
        dst = work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(changed, encoding="utf-8")
        patched.append(str(dst))
        diff += difflib.unified_diff(text.splitlines(True), changed.splitlines(True),
                                     f"a/{rel.as_posix()}", f"b/{rel.as_posix()}")
    (out / "patch.diff").write_text("".join(diff), encoding="utf-8")
    r = subprocess.run(["javac", "-nowarn", "-encoding", "UTF-8", "-cp", str(JAR), "-d", str(classes), *patched],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("javac failed:\n" + r.stderr)


def ensure_built() -> None:
    if not JAR.is_file():
        subprocess.check_call(["bash", str(ROOT / "scripts/install-jmrtd-local.sh")], cwd=ROOT)
        subprocess.check_call(["mvn", "-q", "-DskipTests", "package"], cwd=ROOT / "drivers/jmrtd")
    if not CHIP.is_file():
        subprocess.check_call(["go", "build", "-o", str(CHIP), "./cmd/chip-serve"], cwd=ROOT)


def run_entry(entry: dict, cp: str, logdir: Path, suite_id: str) -> dict:
    logdir.mkdir(parents=True, exist_ok=True)
    cmd = ["java", "-cp", cp, "org.callerboundary.jmrtd.JmrtdRead",
           "-profile", str(ROOT / entry["profile"]), "-variant", entry["variant"],
           "-suite-id", suite_id, "-suite-seed", "1", "-suite-n", "1", "-run-index", "1",
           "-integrator", entry["integrator"], "-chip-serve", str(CHIP), "-log-dir", str(logdir)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
    arts = sorted(logdir.glob("*.json"), key=os.path.getmtime)
    if not arts:
        return {"outcome": "NO_ARTIFACT", "err": r.stderr[-300:]}
    d = json.loads(arts[-1].read_text())
    return {"outcome": d.get("outcome"), "step_exception": d.get("step_exception")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=sorted(PATCH_SETS), required=True)
    ap.add_argument("manifests", nargs="+")
    x = ap.parse_args()
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = ROOT / f"analysis/data/jmrtd-patch-{x.set}-{ts}"
    out.mkdir(parents=True)
    work, classes = Path(f"/tmp/jmrtd-patch-{x.set}-src"), Path(f"/tmp/jmrtd-patch-{x.set}-classes")
    ensure_built()
    prepare(PATCH_SETS[x.set], work, classes, out)
    entries = []
    for m in x.manifests:
        entries += [e for e in json.loads((ROOT / m).read_text())["entries"] if e.get("library") == "jmrtd"]
    print(f"{x.set}: {len(entries)} JMRTD entries", flush=True)
    rows = []
    for i, e in enumerate(entries, 1):
        un = run_entry(e, str(JAR), out / "unpatched" / e["scenario_id"], f"patch-{x.set}")
        pa = run_entry(e, f"{classes}{os.pathsep}{JAR}", out / "patched" / e["scenario_id"], f"patch-{x.set}")
        rows.append({"scenario": e["scenario_id"], "cell": e.get("cell"), "test_case": e.get("test_case"),
                     "integrator": e["integrator"], "expect_outcome": e.get("expect_outcome"),
                     "unpatched": un["outcome"], "patched": pa["outcome"],
                     "patched_step_exception": pa.get("step_exception"), "changed": un["outcome"] != pa["outcome"]})
        print(f"[{i}/{len(entries)}] {e['scenario_id']}: {un['outcome']} -> {pa['outcome']}", flush=True)
    roll: dict = {}
    for r in rows:
        k = f"{r['cell']}/{r['integrator']}"
        roll.setdefault(k, {"unpatched": Counter(), "patched": Counter()})
        roll[k]["unpatched"][r["unpatched"]] += 1
        roll[k]["patched"][r["patched"]] += 1
    summary = {"set": x.set, "ts": ts, "manifests": x.manifests, "n_entries": len(rows),
               "changed": [r["scenario"] for r in rows if r["changed"]],
               "rollup": {k: {a: dict(c) for a, c in v.items()} for k, v in roll.items()}, "rows": rows}
    (out / "SUMMARY.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(f"changed: {len(summary['changed'])} of {len(rows)}\nOUT: {out}", flush=True)


if __name__ == "__main__":
    main()
