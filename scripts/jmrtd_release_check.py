#!/usr/bin/env python3
"""Run JMRTD suite entries on the pinned release (0.8.9) and on a newer release, to measure an upstream fix.

The driver is built a second time, in a copy of drivers/jmrtd whose pom names the newer release, so both
runs use the same driver source and differ only in the JMRTD release (and the dependencies that release
declares). Every JMRTD entry of the given manifests runs once with each driver jar, as in
jmrtd_patch_check.py. Writes analysis/data/jmrtd-release-<version>-<ts>/SUMMARY.json.

Usage (from the harness root, vsmartcard.env sourced for independent-chip entries):
  python3 scripts/jmrtd_release_check.py --version 0.8.10 suites/pace.json suites/ca-aa.json ...

Predictions for 0.8.10 (from its source, before the run): JMRTD bug #90, doAA under propagate is surfaced
for all 13 rejected INTERNAL AUTHENTICATE status words on both chips (6700 included, because 0.8.10 also
unwraps a protected 67xx); doAA under catch-continue stays silent (the integrator catches it). Chip
Authentication under catch-continue for 6700, 6F00 and 6FFF moves from surfaced (later SM read error) to
silent, because the send sequence counter now stays in step. JMRTD bug #91, the four malformed step-4
entries of u6-jmrtd move from silent to surfaced. Every other entry is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jmrtd_patch_check import JAR, ROOT, ensure_built, run_entry  # noqa: E402

PINNED = "0.8.9"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def embedded_version(jar: Path) -> str:
    with zipfile.ZipFile(jar) as z:
        props = z.read("META-INF/maven/org.jmrtd/jmrtd/pom.properties").decode()
    return re.search(r"^version=(.+)$", props, re.M).group(1).strip()


def build_release_jar(version: str, work: Path) -> Path:
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(ROOT / "drivers/jmrtd", work, ignore=shutil.ignore_patterns("target"))
    pom = work / "pom.xml"
    text = pom.read_text(encoding="utf-8")
    old = f"<artifactId>jmrtd</artifactId>\n      <version>{PINNED}</version>"
    assert text.count(old) == 1, f"pom anchor appears {text.count(old)}x, not 1"
    pom.write_text(text.replace(old, f"<artifactId>jmrtd</artifactId>\n      <version>{version}</version>"),
                   encoding="utf-8")
    subprocess.check_call(["mvn", "-q", "-DskipTests", "package"], cwd=work)
    jar = work / "target/jmrtd-driver-0.1.0.jar"
    assert jar.is_file(), "release driver jar missing after build"
    return jar


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("manifests", nargs="+")
    x = ap.parse_args()
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = ROOT / f"analysis/data/jmrtd-release-{x.version}-{ts}"
    out.mkdir(parents=True)
    ensure_built()
    rel_jar = build_release_jar(x.version, Path(f"/tmp/jmrtd-release-{x.version}-driver"))
    m2 = Path.home() / ".m2/repository/org/jmrtd/jmrtd"
    prov = {
        "pinned": {"version": embedded_version(JAR), "driver_jar_sha256": sha256(JAR),
                   "jmrtd_jar_sha256": sha256(m2 / PINNED / f"jmrtd-{PINNED}.jar")},
        "release": {"version": embedded_version(rel_jar), "driver_jar_sha256": sha256(rel_jar),
                    "jmrtd_jar_sha256": sha256(m2 / x.version / f"jmrtd-{x.version}.jar")},
    }
    assert prov["pinned"]["version"] == PINNED, prov
    assert prov["release"]["version"] == x.version, prov
    print(json.dumps(prov), flush=True)
    entries = []
    for m in x.manifests:
        entries += [e for e in json.loads((ROOT / m).read_text())["entries"] if e.get("library") == "jmrtd"]
    print(f"release {x.version}: {len(entries)} JMRTD entries", flush=True)
    rows = []
    for i, e in enumerate(entries, 1):
        sid = f"release-{x.version}"
        a = run_entry(e, str(JAR), out / PINNED / e["scenario_id"], sid)
        b = run_entry(e, str(rel_jar), out / x.version / e["scenario_id"], sid)
        rows.append({"scenario": e["scenario_id"], "cell": e.get("cell"), "test_case": e.get("test_case"),
                     "integrator": e["integrator"], "expect_outcome": e.get("expect_outcome"),
                     PINNED: a["outcome"], x.version: b["outcome"],
                     "release_step_exception": b.get("step_exception"), "changed": a["outcome"] != b["outcome"]})
        print(f"[{i}/{len(entries)}] {e['scenario_id']}: {a['outcome']} -> {b['outcome']}", flush=True)
    roll: dict = {}
    for r in rows:
        k = f"{r['cell']}/{r['integrator']}"
        roll.setdefault(k, {PINNED: Counter(), x.version: Counter()})
        roll[k][PINNED][r[PINNED]] += 1
        roll[k][x.version][r[x.version]] += 1
    summary = {"version": x.version, "pinned": PINNED, "ts": ts, "manifests": x.manifests, "provenance": prov,
               "n_entries": len(rows), "changed": [r["scenario"] for r in rows if r["changed"]],
               "rollup": {k: {a: dict(c) for a, c in v.items()} for k, v in roll.items()}, "rows": rows}
    (out / "SUMMARY.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(f"changed: {len(summary['changed'])} of {len(rows)}\nOUT: {out}", flush=True)


if __name__ == "__main__":
    main()
