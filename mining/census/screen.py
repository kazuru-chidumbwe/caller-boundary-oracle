#!/usr/bin/env python3
"""Census steps 3 and 4 on shallow clones (run on a Linux host with git).

Usage: python3 mining/census/screen.py [--workdir /tmp/census]   (reads candidates.csv, writes screen.csv)
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = re.compile(r"\.(go|java|kt|cs|dart|swift|m|py|rs|js|ts|c|cc|cpp|h)$")
PACE_INFO = re.compile(r"0\.4\.0\.127\.0\.7\.2\.2\.4|04\s*,?\s*0x00|04007F0007020204|PACEInfo|PaceInfo|PACE_INFO|pace_info|PACEInfo", re.I)
PACE_OID_BYTES = re.compile(r"0x04,\s*0x00,\s*0x7[fF],\s*0x00,\s*0x07,\s*0x02,\s*0x02,\s*0x04")
PACE_MAP = re.compile(r"(generic|integrated)[ _-]?mapping|map[ _-]?nonce|\bGM_|_GM\b|ECDH[-_]GM|DH[-_]GM|ECDH_GM|PACE_ECDH|mapping.?type", re.I)


def files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and CODE.search(p.name) and p.stat().st_size < 2_000_000 and ".git" not in p.parts:
            yield p


def is_library(root: Path) -> tuple[bool, str]:
    def has(pattern):
        return [p for p in root.rglob(pattern) if ".git" not in p.parts]
    for gm in has("go.mod"):
        pkgs = {p.parent for p in gm.parent.rglob("*.go") if not p.name.endswith("_test.go")}
        if any(not re.search(r"^package main\b", next((l for l in p.read_text(errors="ignore").splitlines() if l.startswith("package ")), ""), re.M)
               for d in pkgs for p in list(d.glob("*.go"))[:1]):
            return True, f"go module {gm.relative_to(root)}"
    for f in has("pom.xml") + has("build.gradle") + has("build.gradle.kts"):
        t = f.read_text(errors="ignore")
        if re.search(r"java-library|com\.android\.library|maven-publish|<packaging>jar|<artifactId>", t):
            return True, f"java/kotlin build {f.relative_to(root)}"
    for f in has("*.csproj"):
        t = f.read_text(errors="ignore")
        if "<OutputType>Exe" not in t and "<OutputType>WinExe" not in t:
            return True, f".NET project {f.relative_to(root)}"
    for f in has("pubspec.yaml"):
        lib = f.parent / "lib"
        if lib.is_dir() and not (lib / "main.dart").exists():
            return True, f"Dart package {f.relative_to(root)}"
    if has("Package.swift") or has("*.podspec"):
        return True, "Swift package or podspec"
    for f in has("Cargo.toml"):
        t = f.read_text(errors="ignore")
        if "[lib]" in t or (f.parent / "src" / "lib.rs").exists():
            return True, f"Rust library {f.relative_to(root)}"
    if has("setup.py") or has("pyproject.toml") or has("setup.cfg"):
        return True, "Python package"
    for f in has("package.json"):
        t = f.read_text(errors="ignore")
        if re.search(r'"(main|exports)"\s*:', t) and '"private": true' not in t:
            return True, f"npm package {f.relative_to(root)}"
    return False, "no package metadata for a library"


def screen(repo: str, url: str, work: Path) -> dict:
    dest = work / repo.replace("/", "__")
    shutil.rmtree(dest, ignore_errors=True)
    r = subprocess.run(["git", "clone", "-q", "--depth", "1", url, str(dest)], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return {"repo": repo, "pace": "unknown", "library": "unknown", "evidence": "", "note": "clone failed: " + r.stderr.strip()[:120]}
    info, mapping = [], []
    for p in files(dest):
        t = p.read_text(errors="ignore")
        if PACE_INFO.search(t) or PACE_OID_BYTES.search(t):
            info.append(str(p.relative_to(dest)))
        if PACE_MAP.search(t):
            mapping.append(str(p.relative_to(dest)))
    pace = bool(info) and bool(mapping)
    lib, why = is_library(dest)
    shutil.rmtree(dest, ignore_errors=True)
    note = "" if pace else ("PACE structures but no mapping code" if info else "no PACE implementation found")
    if pace and not lib:
        note = "application, not a library (" + why + ")"
    return {"repo": repo, "pace": "yes" if pace else "no", "library": "yes" if lib else "no",
            "evidence": "; ".join((info[:2] + mapping[:2])), "note": note if not (pace and lib) else why}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", type=Path, default=Path("/tmp/census"))
    a = ap.parse_args()
    a.workdir.mkdir(parents=True, exist_ok=True)
    cand = [c for c in csv.DictReader((HERE / "candidates.csv").open(encoding="utf-8")) if c["on_topic"] == "True"]
    out = []
    for i, c in enumerate(cand, 1):
        try:
            out.append(screen(c["repo"], c["url"], a.workdir))
        except subprocess.TimeoutExpired:
            out.append({"repo": c["repo"], "pace": "unknown", "library": "unknown", "evidence": "", "note": "clone timed out"})
        if i % 25 == 0:
            print(f"{i}/{len(cand)}", flush=True)
    with (HERE / "screen.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["repo", "pace", "library", "evidence", "note", "studied"])
        w.writeheader()
        for r in out:
            w.writerow(r)
    print("pace yes:", sum(r["pace"] == "yes" for r in out), " library among them:", sum(r["pace"] == "yes" and r["library"] == "yes" for r in out))


if __name__ == "__main__":
    main()
