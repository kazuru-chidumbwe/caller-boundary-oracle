#!/usr/bin/env python3
"""Reachability probe for the mutation sites (mutation/DESIGN.md, change 6).

For each library version, every site that has a mutant gets one marker statement that prints
`CBOPROBE:<site>:` when the line is reached. All markers of a library version go into one build
of a separate copy of the source; the reduced suite then runs once and records which markers
appeared on which run. Sites where a marker cannot be placed as a statement, or whose marker the
compiler rejects, are reported as "not placed" and their reachability as unknown.

Usage (lab):  bash mutation/run.sh is not used; run with the same environment:
              PATH=/usr/local/go/bin:$PATH; source ../_vendor/*.env; python3 mutation/probe.py
Output: mutation/out/reach.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import signal
import os
import subprocess
import time
from collections import defaultdict
from pathlib import Path

from run_mutants import ROOT, Library, entries_for, JMRTD_JAR, sh
from run_suite import common_flags

MARK = {
    "go": 'println("CBOPROBE:{sid}:")',
    "java": 'System.err.println("CBOPROBE:{sid}:");',
    "cs": 'System.Console.Error.WriteLine("CBOPROBE:{sid}:");',
    "dart": 'print("CBOPROBE:{sid}:");',
}
LANG = {"gmrtd": "go", "jmrtd": "java", "emrtd-dotnet": "cs", "dmrtd": "dart"}
HEADER = re.compile(r"^(\}|catch\b|on\s|else\b|finally\b)")
ERR_LINE = {
    "go": re.compile(r"([\w./-]+\.go):(\d+):\d+"),
    "java": re.compile(r"([\w./-]+\.java):(\d+):"),
    "cs": re.compile(r"([\w./\\-]+\.cs)\((\d+),\d+\)"),
    "dart": re.compile(r"([\w./-]+\.dart):(\d+):\d+"),
}


def placement(lines: list[str], idx: int, lang: str) -> tuple[str, int] | None:
    """Where to put the marker for the site on line idx (0-based): ('before', idx) or ('after_brace', idx)."""
    s = lines[idx].strip()
    if HEADER.match(s):
        return ("after_brace", idx)
    j = idx - 1
    while j >= 0 and (not lines[j].strip() or lines[j].strip().startswith(("//", "*", "/*", "#"))):
        j -= 1
    prev = lines[j].rstrip() if j >= 0 else "{"
    if lang == "go":
        ok = not prev.endswith(("(", ",", "+", "-", "*", "/", "&&", "||", "=", "."))
    else:
        ok = prev.endswith((";", "{", "}", ":")) or prev.lstrip().startswith(("//", "*", "/*"))
    return ("before", idx) if ok else None


def insert_markers(path: Path, sites: list[tuple[str, int]], lang: str) -> dict[str, str]:
    """Insert one marker per (site_id, line). Returns site_id -> 'placed' or a reason."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    status, edits = {}, []
    for sid, line in sites:
        where = placement(lines, line - 1, lang)
        if where is None:
            status[sid] = "not placed: continuation line"
            continue
        kind, idx = where
        mark = MARK[lang].format(sid=sid)
        if kind == "before":
            indent = re.match(r"\s*", lines[idx]).group(0)
            edits.append((idx, "before", indent + mark))
        else:
            k = idx
            while k < len(lines) and "{" not in lines[k]:
                k += 1
            if k == len(lines):
                status[sid] = "not placed: no block"
                continue
            edits.append((k, "after_brace", mark))
        status[sid] = "placed"
    for idx, kind, mark in sorted(edits, key=lambda e: -e[0]):
        if kind == "before":
            lines.insert(idx, mark)
        else:
            pos = lines[idx].rfind("{")
            lines[idx] = lines[idx][: pos + 1] + " " + mark + " " + lines[idx][pos + 1:]
    path.write_text("\n".join(lines), encoding="utf-8", newline="")
    return status


def build(lib: Library, changed: list[str]) -> tuple[bool, str]:
    if lib.name != "jmrtd":
        return lib.build(None)
    lib.prepare()
    classes = lib.bin / "classes"
    shutil.rmtree(classes, ignore_errors=True)
    classes.mkdir()
    return lib._ok(sh(["javac", "-nowarn", "-encoding", "UTF-8", "-cp", str(JMRTD_JAR), "-d", str(classes),
                       *[str(lib.work / c) for c in changed]], ROOT))


def run_all(lib: Library, entries: list[dict], timeout: int, tmp: Path) -> dict[str, list[str]]:
    reached = {}
    for e in entries:
        log_dir = tmp / e["scenario_id"]
        shutil.rmtree(log_dir, ignore_errors=True)
        log_dir.mkdir(parents=True)
        flags = ["-log-dir", str(log_dir), *common_flags(e, {"suite_id": "probe", "seed": 1}, ROOT / e["profile"], 1, 1)]
        p = subprocess.Popen(lib.command(e, flags), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             start_new_session=True)
        try:
            out, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            out, _ = p.communicate()
        reached[e["scenario_id"]] = sorted(set(re.findall(r"CBOPROBE:(M1-\d+):", out.decode("utf-8", "replace"))))
    return reached


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vendor", type=Path, default=ROOT.parent / "_vendor")
    ap.add_argument("--out", type=Path, default=ROOT.parent / "mutprobe")
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args()
    reduced = json.loads((ROOT / "mutation/reduced.json").read_text(encoding="utf-8"))["entries"]
    mutants = [json.loads(l) for l in (ROOT / "mutation/mutants.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    groups: dict[tuple[str, str], dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for m in mutants:
        if m["status"] == "ok":
            groups[(m["library"], m["version"])][m["file"]].add((m["site_id"], m["line"]))
    result = {}
    for (name, version), files in sorted(groups.items()):
        lib = Library(name, version, a.vendor, a.out)
        lang = LANG[name]
        originals = {f: (lib.work / f).read_bytes() for f in files}
        status = {}
        try:
            for f, sites in files.items():
                status |= insert_markers(lib.work / f, sorted(sites), lang)
            for attempt in range(6):
                ok, msg = build(lib, sorted(files))
                if ok:
                    break
                bad = set()
                for fname, ln in ERR_LINE[lang].findall(msg):
                    for f in files:
                        if f.endswith(fname.replace("\\", "/").split("/")[-1]):
                            text = (lib.work / f).read_text(encoding="utf-8", errors="replace").split("\n")
                            near = "\n".join(text[max(0, int(ln) - 3): int(ln) + 2])
                            bad |= set(re.findall(r"CBOPROBE:(M1-\d+):", near))
                if not bad:
                    raise SystemExit(f"probe build failed for {name} {version} and no marker is to blame:\n{msg[-2000:]}")
                for f in files:
                    (lib.work / f).write_bytes(originals[f])
                for sid in bad:
                    status[sid] = "not placed: compiler rejected the marker"
                for f, sites in files.items():
                    keep = sorted(s for s in sites if status.get(s[0]) == "placed")
                    insert_markers(lib.work / f, keep, lang)
            else:
                raise SystemExit(f"probe build for {name} {version} still failing after retries")
            entries = entries_for(reduced, name, version, None)
            reached = run_all(lib, entries, a.timeout, a.out / "runs" / f"{name}-{version}")
        finally:
            for f in files:
                (lib.work / f).write_bytes(originals[f])
            lib.build(None) if name != "jmrtd" else None
        result[f"{name}-{version}"] = {"status": status, "reached": reached}
        n_placed = sum(v == "placed" for v in status.values())
        n_reached = len({s for ss in reached.values() for s in ss})
        print(f"{time.strftime('%H:%M:%S')} {name} {version}: {len(status)} sites, {n_placed} probed, {n_reached} reached", flush=True)
    out = ROOT / "mutation" / "out" / "reach.json"
    out.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
