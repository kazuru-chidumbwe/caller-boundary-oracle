#!/usr/bin/env python3
"""U1: how gmrtd's RequireAuthenticDocument (v1.4.0, PR #537) changes CA and AA failure reporting.

Builds cmd/gmrtd-read against each release in analysis/u1_expectations.json (build tag
gmrtd_sweep_authentic) and the v1.3.2 reference (default arm only), runs every group's profiles
in its arm, and compares each run with the expectations committed before the run.

Usage (lab):  GOTOOLCHAIN=go1.26.10 python3 analysis/u1_authentic.py --vendor ../_vendor --out ../u1-run
Output: <out>/u1-results.json, <out>/U1-RESULT.md, <out>/runs/<release>/<arm>/<profile>/*.json
Exit status 3 when a positive control fails (the run is then invalid).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = "github.com/kazuru-chidumbwe/caller-boundary-oracle"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def build(tag: str, vendor: Path, out: Path, buildtag: str) -> Path:
    gm = vendor / "gmrtd"
    wt = vendor / f"gmrtd-{tag}"
    if not wt.exists():
        git(gm, "worktree", "add", "-q", str(wt), tag)
    sha = git(wt, "rev-parse", "HEAD")
    base = (ROOT / "gomod" / "gmrtd-b861835.mod").read_text(encoding="utf-8")
    lines = [l for l in base.splitlines() if not l.startswith("replace github.com/gmrtd/gmrtd")]
    lines.append(f"replace github.com/gmrtd/gmrtd => {wt}")
    mod = out / "gomod" / f"{tag}.mod"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (mod.with_suffix(".sum")).write_bytes((ROOT / "gomod" / "gmrtd-b861835.sum").read_bytes())
    exe = out / "bin" / tag / "gmrtd-read"
    exe.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GOFLAGS="-mod=mod")
    p = subprocess.run(["go", "build", f"-modfile={mod}", f"-tags={buildtag}",
                        "-ldflags", f"-X {MODULE}/internal/gmrtdcompat.Commit={sha}", "-o", str(exe), "./cmd/gmrtd-read"],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    (exe.parent / "build.log").write_text(p.stdout + p.stderr, encoding="utf-8")
    if p.returncode != 0:
        sys.exit(f"build {tag} failed, see {exe.parent / 'build.log'}")
    return exe


def run(exe: Path, profile: str, arm: str, flags: dict, log_dir: Path) -> dict:
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(exe), "-profile", profile, "-log-dir", str(log_dir), "-variant", arm]
    if flags["guard"]:
        cmd.append("-guard")
    if flags["require_authentic"]:
        cmd.append("-require-authentic")
    if flags["trusted_chain"]:
        cmd.append("-trusted-chain")
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
    files = sorted(log_dir.glob("*.json"))
    if p.returncode != 0 or not files:
        return {"harness_error": (p.stdout + p.stderr).strip()}
    a = json.loads(files[-1].read_text(encoding="utf-8"))
    o = a["observation"]
    return {"outcome": a["outcome"], "read_err": a.get("read_document_err", ""), "fired": o.get("fired"),
            "failed": o.get("failed"), "succeeded": o.get("succeeded"), "returned_error": o.get("returned_error"),
            "chip_auth_err": a.get("chip_auth_err", ""), "active_auth_err": a.get("active_auth_err", ""),
            "artifact": str(files[-1].relative_to(log_dir.parents[3]))}


def check(r: dict, want: str) -> bool:
    if "harness_error" in r:
        return False
    return {"status_only": r["outcome"] == "status_only", "surfaced": r["outcome"] == "surfaced",
            "not_applicable": r["outcome"] == "not_applicable",
            "no_error": r["read_err"] == "", "error": r["read_err"] != "", "succeeded": bool(r["succeeded"]),
            "failed": bool(r["failed"]), "not_fired": not r["fired"]}[want]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--expectations", type=Path, default=ROOT / "analysis" / "u1_expectations.json",
                    help="expectations file (default: the U1 file; R1 uses analysis/r1_expectations.json)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    exp = json.loads(a.expectations.read_text(encoding="utf-8"))
    head = git(ROOT, "rev-parse", "HEAD")
    if git(ROOT, "status", "--porcelain", "--untracked-files=no"):
        sys.exit("harness tree is dirty; commit first")
    go = subprocess.run(["go", "version"], capture_output=True, text=True).stdout.strip()
    results = {"harness": head, "go": go, "releases": {}, "groups": []}

    ref = build(exp["reference_release"], a.vendor, a.out, "gmrtd_sweep_optin")
    refruns = {}
    for g in exp["groups"]:
        if g["arm"] != "default":
            continue
        for pat in g["profiles"]:
            for prof in sorted(glob.glob(str(ROOT / pat))):
                rel = str(Path(prof).relative_to(ROOT)).replace(os.sep, "/")
                refruns[rel] = run(ref, rel, "default", exp["arms"]["default"],
                                   a.out / "runs" / exp["reference_release"] / "default" / Path(rel).stem)
    results["reference"] = refruns

    control_fail = False
    for tag in exp["releases"]:
        exe = build(tag, a.vendor, a.out, "gmrtd_sweep_authentic")
        results["releases"][tag] = git(a.vendor / f"gmrtd-{tag}", "rev-parse", "HEAD")
        for g in exp["groups"]:
            for pat in g["profiles"]:
                for prof in sorted(glob.glob(str(ROOT / pat))):
                    rel = str(Path(prof).relative_to(ROOT)).replace(os.sep, "/")
                    r = run(exe, rel, g["arm"], exp["arms"][g["arm"]], a.out / "runs" / tag / g["arm"] / Path(rel).stem)
                    ok = all(check(r, w) for w in g["expect"])
                    if g.get("control") and not ok:
                        control_fail = True
                    results["groups"].append({"group": g["id"], "release": tag, "arm": g["arm"], "profile": rel,
                                              "expect": g["expect"], "as_expected": ok, **r})
            print(f"{tag} {g['id']} done", flush=True)

    (a.out / "u1-results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    lines = ["# U1 result: gmrtd RequireAuthenticDocument (generated by analysis/u1_authentic.py)", "",
             f"Harness {head}; {go}; releases " + ", ".join(f"{t} ({s[:7]})" for t, s in results["releases"].items()) + ".", "",
             "| group | release | arm | cells | as expected | outcomes | read error |", "| --- | --- | --- | ---: | ---: | --- | ---: |"]
    from collections import Counter
    for g in exp["groups"]:
        for tag in exp["releases"]:
            rows = [r for r in results["groups"] if r["group"] == g["id"] and r["release"] == tag]
            oc = Counter(r.get("outcome", "harness_error") for r in rows)
            lines.append(f"| {g['id']} | {tag} | {g['arm']} | {len(rows)} | {sum(r['as_expected'] for r in rows)} | "
                         + ", ".join(f"{k} {v}" for k, v in sorted(oc.items())) + f" | {sum(bool(r.get('read_err')) for r in rows)} |")
    oc = Counter(r.get("outcome", "harness_error") for r in refruns.values())
    lines += ["", f"Reference {exp['reference_release']}, default arm: " + ", ".join(f"{k} {v}" for k, v in sorted(oc.items())) + f" over {len(refruns)} cells.", ""]
    miss = [r for r in results["groups"] if not r["as_expected"]]
    lines.append(f"Mismatches against the committed expectations: {len(miss)}.")
    for r in miss:
        lines.append(f"- {r['group']} {r['release']} {r['arm']} {r['profile']}: outcome {r.get('outcome')}, read error {r.get('read_err') or r.get('harness_error')!r}")
    if control_fail:
        lines.append("\n**A positive control failed: this run is INVALID.**")
    (a.out / "U1-RESULT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    sys.exit(3 if control_fail else 0)


if __name__ == "__main__":
    main()
