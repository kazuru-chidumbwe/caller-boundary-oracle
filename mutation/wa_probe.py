#!/usr/bin/env python3
"""T62 reachability probe (mutation/HELD-OUT-T62.md; frozen probe of mutation/probe.py, DESIGN change 6).

Marker placement, marker text and the retry rule for markers the compiler rejects are those of probe.py,
imported unchanged. Per library, every site with a mutant gets one marker in a separate copy of the source,
the library is built once, every case runs once in every arm, and the markers printed on each run are
recorded. Output is in the form per_arm.py reads (OUT/reach.json: "<library>-x" -> status, reached).

Usage (lab): python3 mutation/wa_probe.py --mutants ../t62/mutants.jsonl --work ../t62/probe --out ../t62/out
             [--placement v2]   (A5-8: else-if conditions and continuation lines; see insert_markers_v2)
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
from probe import ERR_LINE, HEADER, MARK, insert_markers, placement  # noqa: E402  (unchanged frozen placement)
import run_wa_mutants as rw  # noqa: E402

LANG = {"go-webauthn": "go", "java-webauthn-server": "java", "webauthn4j": "java", "fido2-net-lib": "cs"}
SITE = re.compile(r"CBOPROBE:([WX]-\d+):")

# Placement v2 (A5-8, opt-in with --placement v2; v1, the frozen placement of probe.py, stays the default).
# v1 leaves two gaps on these libraries: a site on a continuation line of a multi-line statement gets no marker
# (Fido2: 142 of 274 sites), and a site on an `else if` line gets its marker inside the branch body, so it is seen
# only when the condition is true, not whenever it is evaluated (webauthn4j). v2 changes only those two cases:
#   else if:       an always-true term goes in front of the condition, `else if (<probe> && <cond>)`; since the
#                  term is true, `true && a || b` keeps the meaning of `a || b`, and the line is seen whenever the
#                  condition is evaluated.
#   continuation:  the marker goes before the start of the statement (the nearest earlier line where v1 can place
#                  one), so the site counts as reached when its statement starts. This can count as reached a site
#                  whose sub-expression short-circuiting skipped, never the other way round.
# Every other site keeps exactly its v1 placement.
COND_MARK = {
    "java": '(System.err.printf("CBOPROBE:{sid}:%n") != null) && ',
    "cs": '((System.Func<bool>)(() => {{ System.Console.Error.WriteLine("CBOPROBE:{sid}:"); return true; }}))() && ',
    "go": '(func() bool {{ println("CBOPROBE:{sid}:"); return true }}()) && ',
}
ELSE_IF = re.compile(r"^(\s*(?:\}\s*)?else\s+if\s*\(?)")


def is_placed(v: str) -> bool:
    return v == "placed" or v.startswith("placed:")


def insert_markers_v2(path: Path, sites: list[tuple[str, int]], lang: str) -> dict[str, str]:
    """Like probe.insert_markers, with the two v2 changes above."""
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    status, edits = {}, []
    for sid, line in sites:
        idx = line - 1
        j, moved = idx, False
        if not ELSE_IF.match(lines[idx]) and placement(lines, idx, lang) is None:
            j = idx - 1                       # continuation line: walk back to the statement start
            while j >= 0 and not ELSE_IF.match(lines[j]) and placement(lines, j, lang) is None:
                j -= 1
            if j < 0:
                status[sid] = "not placed: no statement start"
                continue
            moved = True
        m = ELSE_IF.match(lines[j])
        if m:
            head = m.group(1)
            if lang != "go" and not head.rstrip().endswith("("):
                status[sid] = "not placed: else-if condition not on its line"
                continue
            edits.append((j, "cond", len(head), COND_MARK[lang].format(sid=sid)))
            status[sid] = "placed: condition" + (", statement start" if moved else "")
            continue
        s = lines[j].strip()
        if HEADER.match(s):
            if moved:
                status[sid] = "not placed: statement start is a block header"
                continue
            k = j
            while k < len(lines) and "{" not in lines[k]:
                k += 1
            if k == len(lines):
                status[sid] = "not placed: no block"
                continue
            edits.append((k, "after_brace", 0, MARK[lang].format(sid=sid)))
        else:
            indent = re.match(r"\s*", lines[j]).group(0)
            edits.append((j, "before", 0, indent + MARK[lang].format(sid=sid)))
        status[sid] = "placed: statement start" if moved else "placed"
    # bottom-up; on one line the in-place edits (condition, after brace) come before inserting lines above it
    for idx, kind, col, mark in sorted(edits, key=lambda e: (-e[0], e[1] == "before")):
        if kind == "before":
            lines.insert(idx, mark)
        elif kind == "cond":
            lines[idx] = lines[idx][:col] + mark + lines[idx][col:]
        else:
            pos = lines[idx].rfind("{")
            lines[idx] = lines[idx][: pos + 1] + " " + mark + " " + lines[idx][pos + 1:]
    path.write_text("\n".join(lines), encoding="utf-8", newline="")
    return status


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
    ap.add_argument("--placement", choices=("v1", "v2"), default="v1",
                    help="v1: frozen probe.py placement (default); v2: A5-8 placement for else-if and continuation lines")
    a = ap.parse_args()
    insert = insert_markers if a.placement == "v1" else insert_markers_v2
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
                status |= insert(lib.src / f, sorted(sites), lang)
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
                    insert(lib.src / f, sorted(s for s in sites if is_placed(status.get(s[0], ""))), lang)
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
        n_placed = sum(is_placed(v) for v in status.values())
        n_reached = len({s for ss in reached.values() for s in ss})
        print(f"{time.strftime('%H:%M:%S')} {name}: {len(status)} sites, {n_placed} probed, {n_reached} reached", flush=True)
    (a.out / "reach.json").write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    print("wrote", a.out / "reach.json")


if __name__ == "__main__":
    main()
