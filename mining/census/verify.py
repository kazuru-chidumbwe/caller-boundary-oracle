#!/usr/bin/env python3
"""Census check of the step-4 list: wire PACE and lineage, on shallow clones (run on a Linux host).

For every repository that passed step 4 (and every on-topic repository that passed step 3 but
failed the step-4 package rule), record:

  wire      the code sends PACE on the wire: an MSE:Set AT (INS 22, P1P2 C1A4) and a General
            Authenticate (INS 86) command are both built somewhere in non-test code
  lineage   the code is a copy or port of another implementation: the file layout or the
            copyright and package names of NFCPassportReader (AndyQ), dmrtd (ZeroPass), JMRTD
            (org.jmrtd) or OpenPACE appear in the non-test code
  wraps     the repository calls one of those libraries instead of containing its own PACE

Usage: python3 mining/census/verify.py [--workdir /tmp/census-verify]   (writes verify.csv)
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
TEST = re.compile(r"(^|/)(tests?|Tests?|spec|__tests__|example|examples|Examples?)(/|$)|_test\.|Test\.|\.test\.|Tests?\.swift$")
MSE = re.compile(r"0x22\s*,\s*0x[cC]1\s*,\s*0x[aA]4|22\s*[cC]1\s*[aA]4|INS_MSE|MSE_SET_AT|mseSetAT|sendMSESetAT|MSESetAT|setAT|SET_AT|\bmse\b.*\bAT\b", re.I)
GA = re.compile(r"0x86|INS_GENERAL_AUTHENTICATE|GENERAL_AUTHENTICATE|generalAuthenticate|GeneralAuthenticate|general_authenticate", re.I)
LINEAGE = [
    ("NFCPassportReader", re.compile(r"Created by Andy Qua|AndyQ|PACEHandler|NFCPassportReader", re.I)),
    ("dmrtd", re.compile(r"ZeroPass|package:dmrtd|Crt Vavros|crt\.vavros", re.I)),
    ("JMRTD", re.compile(r"org\.jmrtd|net\.sf\.scuba|JMRTD team|Martijn Oostdijk", re.I)),
    ("OpenPACE", re.compile(r"Frank Morgner|openpace|libeac", re.I)),
]
WRAP = [
    ("NFCPassportReader", re.compile(r"import NFCPassportReader|pod ['\"]NFCPassportReader|AndyQ/NFCPassportReader", re.I)),
    ("dmrtd", re.compile(r"^\s*dmrtd\s*:|package:dmrtd/", re.I | re.M)),
    ("JMRTD", re.compile(r"org\.jmrtd:jmrtd|['\"]org\.jmrtd:|<groupId>org\.jmrtd</groupId>|import org\.jmrtd\.", re.I)),
    ("OpenPACE", re.compile(r"#include\s*<eac/", re.I)),
]


def scan(root: Path) -> dict:
    wire_mse, wire_ga = [], []
    lineage, wraps = {}, {}
    manifests = []
    for p in root.rglob("*"):
        if ".git" in p.parts or not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        rel = str(p.relative_to(root))
        if p.name in ("Package.swift", "pubspec.yaml", "build.gradle", "build.gradle.kts", "pom.xml", "Podfile",
                      "package.json", "Cargo.toml", "go.mod") or p.suffix in (".podspec", ".csproj"):
            t = p.read_text(errors="ignore")
            manifests.append(rel)
            for name, rx in WRAP:
                if rx.search(t):
                    wraps.setdefault(name, rel)
        if not CODE.search(p.name):
            continue
        t = p.read_text(errors="ignore")
        for name, rx in WRAP:
            if rx.search(t):
                wraps.setdefault(name, rel)
        if TEST.search(rel):
            continue
        if MSE.search(t):
            wire_mse.append(rel)
        if GA.search(t) and re.search(r"pace", t, re.I):
            wire_ga.append(rel)
        head = "\n".join(t.splitlines()[:40])
        for name, rx in LINEAGE:
            if rx.search(head) or rx.search(rel):
                lineage.setdefault(name, rel)
    return {"wire": "yes" if wire_mse and wire_ga else "no",
            "mse": "; ".join(wire_mse[:3]), "ga": "; ".join(wire_ga[:3]),
            "lineage": "; ".join(f"{k}: {v}" for k, v in lineage.items()),
            "wraps": "; ".join(f"{k}: {v}" for k, v in wraps.items())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="/tmp/census-verify")
    a = ap.parse_args()
    work = Path(a.workdir)
    work.mkdir(parents=True, exist_ok=True)
    screen = list(csv.DictReader((HERE / "screen.csv").open(encoding="utf-8")))
    rows = []
    for r in screen:
        if r["pace"] != "yes":
            continue
        d = work / r["repo"].replace("/", "__")
        if not d.exists():
            try:
                subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{r['repo']}.git", str(d)],
                               check=False, timeout=900)
            except subprocess.TimeoutExpired:
                shutil.rmtree(d, ignore_errors=True)
        if not d.exists():
            rows.append({"repo": r["repo"], "library": r["library"], "wire": "clone failed"})
            continue
        head = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        rows.append({"repo": r["repo"], "library": r["library"], "commit": head, **scan(d)})
        print(r["repo"], rows[-1]["wire"], rows[-1].get("lineage", ""), "|", rows[-1].get("wraps", ""), flush=True)
    with (HERE / "verify.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["repo", "library", "commit", "wire", "mse", "ga", "lineage", "wraps"])
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
