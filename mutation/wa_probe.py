#!/usr/bin/env python3
"""T62 reachability probe (mutation/HELD-OUT-T62.md; frozen probe of mutation/probe.py, DESIGN change 6).

Marker placement, marker text and the retry rule for markers the compiler rejects are those of probe.py,
imported unchanged. Per library, every site with a mutant gets one marker in a separate copy of the source,
the library is built once, every case runs once in every arm, and the markers printed on each run are
recorded. Output is in the form per_arm.py reads (OUT/reach.json: "<library>-x" -> status, reached).

Usage (lab): python3 mutation/wa_probe.py --mutants ../t62/mutants.jsonl --work ../t62/probe --out ../t62/out
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe import ERR_LINE, insert_markers  # noqa: E402  (unchanged frozen placement)
import run_wa_mutants as rw  # noqa: E402

LANG = {"go-webauthn": "go", "java-webauthn-server": "java", "webauthn4j": "java", "fido2-net-lib": "cs"}
SITE = re.compile(r"CBOPROBE:(W-\d+):")


def build(lib: rw.Lib, files: list[str]) -> tuple[bool, str]:
    if LANG[lib.name] != "java":
        return lib.build(None)
    lib.prepare()
    classes = lib.bin / "classes"
    shutil.rmtree(classes, ignore_errors=True)
    classes.mkdir()
    cp = f"{rw.WA}/webauthn/drivers/java/target/webauthn-drivers-1.0.0.jar:{rw.WA}/webauthn/drivers/java/target/lib/*"
    cmd = ["javac", "-nowarn", "-encoding", "UTF-8", "-proc:full", "-cp", ":".join([cp, str(rw.LOMBOK), *map(str, rw.COMPILE_ONLY)]),
           "-processorpath", str(rw.LOMBOK), "-Xmaxerrs", "10000", "-d", str(classes), *[str(lib.src / f) for f in files]]
    p = subprocess.run(cmd, cwd=lib.src, capture_output=True, text=True, timeout=1800)
    return p.returncode == 0, p.stdout + p.stderr   # full output: the error lines name the rejected markers


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args()
    a.work, a.out = a.work.resolve(), a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    cases_dir = a.work / "cases"
    if not cases_dir.exists():
        subprocess.run([str(rw.VENDOR / "webauthn-venv/bin/python"), str(rw.ROOT / "webauthn/authenticator.py"),
                        "--out", str(cases_dir)], check=True)
    cases = sorted(p for p in cases_dir.iterdir() if p.is_dir())
    groups: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for l in a.mutants.read_text(encoding="utf-8").splitlines():
        m = json.loads(l) if l.strip() else None
        if m and m["status"] == "ok" and m["library"] in LANG:
            groups[m["library"]][m["file"]].add((m["site_id"], m["line"]))
    result = {}
    prev = a.out / "reach.json"
    result = json.loads(prev.read_text(encoding="utf-8")) if prev.exists() else {}
    for name, files in groups.items():
        if f"{name}-x" in result:
            continue                      # done in an earlier invocation
        lib = rw.Lib(name, a.work)
        lang = LANG[name]
        originals = {f: (lib.src / f).read_bytes() for f in files}
        status: dict[str, str] = {}
        try:
            for f, sites in files.items():
                status |= insert_markers(lib.src / f, sorted(sites), lang)
            for attempt in range(8):
                ok, msg = build(lib, sorted(files))
                if ok:
                    break
                bad = set()
                for fname, ln in ERR_LINE[lang].findall(msg):
                    for f in files:
                        if f.endswith(fname.replace("\\", "/").split("/")[-1]):
                            text = (lib.src / f).read_text(encoding="utf-8", errors="replace").split("\n")
                            bad |= set(SITE.findall("\n".join(text[max(0, int(ln) - 3): int(ln) + 2])))
                if not bad:
                    raise SystemExit(f"probe build failed for {name} and no marker is to blame:\n{msg[-2000:]}")
                for f in files:
                    (lib.src / f).write_bytes(originals[f])
                for sid in bad:
                    status[sid] = "not placed: compiler rejected the marker"
                for f, sites in files.items():
                    insert_markers(lib.src / f, sorted(s for s in sites if status.get(s[0]) == "placed"), lang)
            else:
                raise SystemExit(f"probe build for {name} still failing after retries")
            reached = {}
            for arm in rw.ARMS[name]:
                for c in cases:
                    case = json.loads((c / "report.json").read_text(encoding="utf-8"))["case"]
                    sid = f"{'CTRL-' if rw.is_control(case) else ''}{case}-{name}-{arm}"
                    try:
                        p = subprocess.run(lib.command(arm) + [str(c)], capture_output=True, text=True, timeout=a.timeout)
                        out = p.stdout + p.stderr
                    except subprocess.TimeoutExpired as e:
                        out = (e.stdout or b"").decode("utf-8", "replace") + (e.stderr or b"").decode("utf-8", "replace")
                    reached[sid] = sorted(set(SITE.findall(out)))
        finally:
            for f in files:
                (lib.src / f).write_bytes(originals[f])
        result[f"{name}-x"] = {"status": status, "reached": reached}
        (a.out / "reach.json").write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
        n_placed = sum(v == "placed" for v in status.values())
        n_reached = len({s for ss in reached.values() for s in ss})
        print(f"{time.strftime('%H:%M:%S')} {name}: {len(status)} sites, {n_placed} probed, {n_reached} reached", flush=True)
    (a.out / "reach.json").write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    print("wrote", a.out / "reach.json")


if __name__ == "__main__":
    main()
