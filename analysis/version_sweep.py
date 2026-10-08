#!/usr/bin/env python3
"""Version sweep of gmrtd: how failure reporting changed release by release (RQ3), and which
oracle sees each real change (RQ1, real-fault replay).

Every gmrtd release from v0.40.0 to v1.3.2 is built with the unchanged driver (internal/gmrtdcompat
picks the API variant that compiles) and run on the PACE, Chip Authentication, Active Authentication
and control profiles, in the default and guard arms, and in the opt-in arm where the release has it.
This is a measurement, not a prediction: no expectations are stated for releases outside the three
pins. A release that does not build is reported with its build log and kept in the table.

Usage (lab):  PATH=/usr/local/go/bin:$PATH python3 analysis/version_sweep.py --vendor ../_vendor --out ../versweep
Output: analysis/out/version-sweep.json and analysis/out/VERSION-SWEEP.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "classifier"))
sys.path.insert(0, str(ROOT / "mutation"))
from run_suite import common_flags, go_flags  # noqa: E402
from score import verdicts  # noqa: E402

FIRST, LAST = "v0.40.0", "v1.3.2"
VARIANTS = ("gmrtd_sweep_optin", "gmrtd_sweep_typed", "gmrtd_sweep_string")
MODULE = "github.com/kazuru-chidumbwe/caller-boundary-oracle"
SKIP = {"artifact-manifest.json", "environment.json"}
SCORED = {"silent", "status_only", "surfaced"}
RANK = {"silent": 0, "status_only": 1, "surfaced": 2}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def releases(repo: Path) -> list[str]:
    tags = git(repo, "tag", "--sort=creatordate").split()
    tags = [t for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    return tags[tags.index(FIRST): tags.index(LAST) + 1]


def entries() -> list[dict]:
    """Template entries: the v1.3.2 entries of the pace, ca-aa and controls suites (gmrtd only)."""
    out = []
    for suite in ("pace", "ca-aa", "controls"):
        for e in json.loads((ROOT / "suites" / f"{suite}.json").read_text(encoding="utf-8"))["entries"]:
            if e["library"] == "gmrtd" and e.get("gmrtd_pin") == "b861835":
                out.append(e)
    return out


def build(tag: str, sha: str, work: Path, out: Path) -> tuple[str | None, str]:
    base = (ROOT / "gomod" / "gmrtd-b861835.mod").read_text(encoding="utf-8")
    lines = [l for l in base.splitlines() if not l.startswith("replace github.com/gmrtd/gmrtd")]
    lines.append(f"replace github.com/gmrtd/gmrtd => {work}")
    moddir = out / "gomod"
    moddir.mkdir(parents=True, exist_ok=True)
    mod = moddir / f"{tag}.mod"
    mod.write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy(ROOT / "gomod" / "gmrtd-b861835.sum", mod.with_suffix(".sum"))
    exe = out / "bin" / tag / "gmrtd-read"
    exe.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GOFLAGS="-mod=mod")
    logs = []
    for variant in VARIANTS:
        p = subprocess.run(["go", "build", f"-modfile={mod}", f"-tags={variant}",
                            "-ldflags", f"-X {MODULE}/internal/gmrtdcompat.Commit={sha}", "-o", str(exe), "./cmd/gmrtd-read"],
                           cwd=ROOT, capture_output=True, text=True, env=env)
        if p.returncode == 0:
            return variant, ""
        logs.append(f"[{variant}] " + (p.stdout + p.stderr)[-1500:])
    return None, "\n".join(logs)


def run(exe: Path, e: dict, arm: dict, log_dir: Path) -> dict:
    shutil.rmtree(log_dir, ignore_errors=True)
    log_dir.mkdir(parents=True)
    entry = dict(e, **arm)
    flags = ["-log-dir", str(log_dir), *common_flags(entry, {"suite_id": "version-sweep", "seed": 1}, ROOT / e["profile"], 1, 1),
             *go_flags(entry)]
    p = subprocess.Popen([str(exe), *flags], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        p.communicate(timeout=60)
        status = "ok" if p.returncode == 0 else "crash"
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        status = "timeout"
    arts = [x for x in log_dir.glob("*.json") if x.name not in SKIP]
    if len(arts) != 1:
        return {"status": status if status != "ok" else "no_artifact"}
    a = json.loads(arts[0].read_text(encoding="utf-8"))
    return {"status": status, "outcome": a.get("outcome"), "observation": a.get("observation"),
            "bac_success": a.get("bac_success"), "access_control": a.get("access_control"),
            "gmrtd_commit": (a.get("provenance") or {}).get("gmrtd_commit")}


def mechanism(e: dict) -> str:
    return "CONTROL" if e["test_case"].startswith("CTRL-") else e["cell"]


def report(data: dict, out_md: Path) -> None:
    tags = list(data)
    lines = ["# gmrtd version sweep (generated by analysis/version_sweep.py)", "",
             f"Releases {tags[0]} to {tags[-1]}: {len(tags)}; built: {sum(1 for t in tags if data[t]['variant'])}.", "",
             "## Behaviour class per release, arm and step (outcomes over all failure kinds)", "",
             "| release | date | arm | PACE | CA | AA | proprietary-parameter control |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for t in tags:
        d = data[t]
        if not d["variant"]:
            lines.append(f"| {t} | {d['date']} | (did not build) | | | | |")
            continue
        for arm in ("default", "guard", "allow-fallback"):
            runs = {k: v for k, v in d["runs"].items() if k.endswith(f"|{arm}")}
            if not runs:
                continue
            cell = defaultdict(Counter)
            for k, r in runs.items():
                case, mech = k.split("|")[0], k.split("|")[1]
                cell[mech][r.get("outcome") or r["status"]] += 1
            prop = next((r for k, r in runs.items() if k.startswith("CTRL-pace-proprietary-params|")), {})
            prop_txt = "refused" if (prop.get("observation") or {}).get("returned_error") else "read"
            fmt = lambda c: ", ".join(f"{o} {n}" for o, n in sorted(c.items())) if c else ""
            lines.append(f"| {t} | {d['date']} | {arm} | {fmt(cell['PACE'])} | {fmt(cell['CA'])} | {fmt(cell['AA'])} | {prop_txt} |")
    lines += ["", "## Real changes between consecutive releases, and which oracle sees them", "",
              "| from | to | arm | step | outcome before | outcome after | entries | any error | output differential | ICAO P4 |",
              "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |"]
    built = [t for t in tags if data[t]["variant"]]
    for a_, b_ in zip(built, built[1:]):
        groups = defaultdict(lambda: [0, Counter()])
        for k, r1 in data[b_]["runs"].items():
            r0 = data[a_]["runs"].get(k)
            if not r0 or r0.get("status") != "ok" or r1.get("status") != "ok":
                continue
            if r0["outcome"] not in SCORED or r1["outcome"] not in SCORED or r0["outcome"] == r1["outcome"]:
                continue
            v0, v1 = verdicts(r0), verdicts(r1)
            case, mech, arm = k.split("|")
            g = groups[(arm, mech, r0["outcome"], r1["outcome"])]
            g[0] += 1
            for o in ("any_error", "output", "p4"):
                if v0[o] != v1[o]:
                    g[1][o] += 1
        for (arm, mech, o0, o1), (n, seen) in sorted(groups.items()):
            lines.append(f"| {a_} | {b_} | {arm} | {mech} | {o0} | {o1} | {n} | {seen['any_error']} | {seen['output']} | {seen['p4']} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vendor", type=Path, default=ROOT.parent / "_vendor")
    ap.add_argument("--out", type=Path, default=ROOT.parent / "versweep")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    out_json = ROOT / "analysis" / "out" / "version-sweep.json"
    if not a.report_only:
        repo = a.vendor / "gmrtd"
        git(repo, "fetch", "-q", "--tags", "origin")
        tmpl = entries()
        data = {}
        for tag in releases(repo):
            sha = git(repo, "rev-list", "-n", "1", tag)
            date = git(repo, "log", "-1", "--format=%cs", tag)
            work = a.out / "src" / tag
            if not work.exists():
                git(repo, "worktree", "add", "-q", "--detach", str(work), sha)
            variant, log = build(tag, sha, work, a.out)
            rec = {"sha": sha, "date": date, "variant": variant, "build_log": log, "runs": {}}
            if variant:
                exe = a.out / "bin" / tag / "gmrtd-read"
                arms = [("default", {"allow_bac_fallback": False, "guard": False}), ("guard", {"allow_bac_fallback": False, "guard": True})]
                if variant == "gmrtd_sweep_optin":
                    arms.append(("allow-fallback", {"allow_bac_fallback": True, "guard": False}))
                for e in tmpl:
                    if e["variant"] != "b861835-default":
                        continue
                    for arm, flags in arms:
                        key = f"{e['test_case']}|{mechanism(e)}|{arm}"
                        rec["runs"][key] = run(exe, e, dict(flags, variant=f"{tag}-{arm}"), a.out / "runs" / tag / key.replace("|", "__"))
            data[tag] = rec
            print(f"{time.strftime('%H:%M:%S')} {tag} ({date}): build {variant or 'FAILED'}, {len(rec['runs'])} runs", flush=True)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(data, indent=1), encoding="utf-8")
    report(json.loads(out_json.read_text(encoding="utf-8")), ROOT / "analysis" / "out" / "VERSION-SWEEP.md")


if __name__ == "__main__":
    main()
