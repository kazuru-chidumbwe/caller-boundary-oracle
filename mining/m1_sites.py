#!/usr/bin/env python3
"""M1 item list: failure-handling sites in the protocol code of each eMRTD library.

A site is a decision point: a line where the library decides what to do with a failure of a
protocol step (PACE, BAC, CA, AA, secure messaging): an error check, a catch, a throw or raise,
or a write of a failure value into a status field. Returns and log calls inside the branch are
what the coder reads (the context column), not separate sites. The patterns and
the files in scope are fixed below and published, so the list is reproducible; coders label
the sites (mining/CODEBOOK.md), they do not search for them.

Sites identical across gmrtd versions (same file, same enclosing function, same normalised
line, same occurrence within the function) are listed once, with the versions they occur in.

Usage: python3 mining/m1_sites.py --vendor ../_vendor --out mining/m1-sites.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import urllib.request
import zipfile
from pathlib import Path

JMRTD_VERSION = "0.8.9"
NFCPR_COMMIT = "6e37f1ab249fef82771da46d32707f2b94ed090f"

# library -> (source roots relative to the vendor dir, files in scope as regexes on the
# path relative to the root, language)
SCOPE = {
    "gmrtd@8fea245": (["gmrtd-8fea245"], r"^(pace|bac|chipauth|activeauth|iso7816|reader|mobile)/[^/]+\.go$", "go"),
    "gmrtd@64bd6ab": (["gmrtd-64bd6ab"], r"^(pace|bac|chipauth|activeauth|iso7816|reader|mobile)/[^/]+\.go$", "go"),
    "gmrtd@b861835": (["gmrtd-b861835"], r"^(pace|bac|chipauth|activeauth|iso7816|reader|mobile|passiveauth)/[^/]+\.go$", "go"),
    "jmrtd@0.8.9": (["jmrtd-sources-0.8.9"], r"^org/jmrtd/(PassportService|AbstractMRTDCardService|protocol/[^/]+)\.java$", "java"),
    "emrtd-dotnet@0433b3a": (["emrtd-dotnet"], r"^src/Emrtd/(Apdu|Bac|DocumentReader|EmrtdSession|Pace|SecureMessaging|Transport|PassiveAuthentication)\.cs$", "cs"),
    "dmrtd@3b6c091": (["dmrtd"], r"^lib/src/(passport|proto/[^/]+|proto/iso7816/[^/]+|com/[^/]+)\.dart$", "dart"),
    "nfcpassportreader@6e37f1a": (["NFCPassportReader-m1"], r"^Sources/NFCPassportReader/[^/]+\.swift$", "swift"),
}

PATTERNS = {
    "go": [
        ("check", r"\bif\s+.*err\s*!=\s*nil"),
        ("raise", r"\bpanic\("),
        ("return_error", r"\breturn\b.*\b(fmt\.Errorf|errors\.New|err)\b"),
        ("status_write", r"\.\w*(Err|Error|Status|Success)\w*\s*=[^=]"),
        ("log", r"\b(log|slog)\.\w+\("),
    ],
    "java": [
        ("catch", r"\bcatch\s*\("),
        ("raise", r"\bthrow\s+new\b|\bthrow\s+\w+;"),
        ("status_write", r"\b\w*(Status|Error|Success|Failed|Result)\w*\s*=[^=]"),
        ("log", r"\b(LOGGER|LOG|log|logger)\.\w+\("),
        ("check", r"\bif\s*\(.*\b(sw|SW_|getSW|status)\w*"),
    ],
    "cs": [
        ("catch", r"\bcatch\b"),
        ("raise", r"\bthrow\b"),
        ("status_write", r"\b\w*(Status|Error|Success|Failed|AccessControl)\w*\s*=[^=>]"),
        ("log", r"\b(log|_log|Log|logger)\w*\??\.?\w*\("),
        ("check", r"\bif\s*\(.*\b(sw|Sw|SW|status|Status)\w*"),
    ],
    "dart": [
        ("catch", r"\bcatch\b|\bon\s+\w+(Exception|Error)\b"),
        ("raise", r"\bthrow\b|\brethrow\b"),
        ("status_write", r"\b\w*(Status|Error|Success|Failed)\w*\s*=[^=>]"),
        ("log", r"\b_log\.\w+\(|\blog\.\w+\("),
        ("check", r"\bif\s*\(.*\b(sw|status)\w*"),
    ],
    "swift": [
        ("catch", r"\bcatch\b"),
        ("raise", r"\bthrow\b"),
        ("status_write", r"\b\w*(Status|Error|Passed|Success|Failed)\w*\s*=[^=]"),
        ("log", r"\bLogger\.\w+\.\w+\(|\bLog\.\w+\("),
        ("check", r"\bif\b.*\bsw[12]\b"),
    ],
}

FUNC = {
    "go": r"^func\s+(?:\([^)]*\)\s*)?(\w+)",
    "java": r"^\s*(?:(?:public|private|protected|static|final|synchronized|abstract)\s+)+[\w<>\[\],.? ]+?\s+(\w+)\s*\(",
    "cs": r"^\s*(?:public|private|protected|internal|static|async|override|virtual|\s)+[\w<>\[\],?\s]+\s+(\w+)\s*\(",
    "dart": r"^\s*(?:static\s+|Future<[^>]*>\s+|void\s+|[\w<>?]+\s+)(\w+)\s*\([^;]*\)\s*(?:async\s*)?\{",
    "swift": r"^\s*(?:@\w+\s+)*(?:public\s+|private\s+|internal\s+|fileprivate\s+|static\s+|override\s+)*func\s+(\w+)",
}
STEP_HINTS = [
    ("PACE", r"pace|PACE|Pace|mapNonce|GeneralAuthenticate|general_authenticate"),
    ("CA", r"chipauth|ChipAuth|chipAuth|ChipAuthentication|CAProtocol|doCA|\bCA\b"),
    ("AA", r"activeauth|ActiveAuth|activeAuth|InternalAuthenticate|internalAuthenticate|AAProtocol|doAA"),
    ("BAC", r"\bbac\b|BAC|Bac|ExternalAuthenticate|MutualAuth|mutualAuth"),
    ("SM", r"secure.?messag|SecureMessag|\bsm\b|unprotect|unwrap|SMWrapper|SecureMessagingWrapper"),
    ("PA", r"passiveauth|PassiveAuth|SOD|verifySignature"),
    ("FILE", r"ReadBinary|readBinary|SelectEF|selectEF|readFile|ReadFile|getInputStream"),
]


IN_SCOPE_STEPS = {"PACE", "BAC", "CA", "AA", "SM"}
FAILURE_VALUE = re.compile(r"fail|\bfalse\b|\.failed\b|\berr|\bnil\b|\bnull\b", re.I)
SUCCESS_VALUE = re.compile(r"=\s*(true|\.success)\b")


def is_decision(kinds: list[str], line: str) -> bool:
    if {"check", "catch", "raise"} & set(kinds):
        return True
    return "status_write" in kinds and bool(FAILURE_VALUE.search(line)) and not SUCCESS_VALUE.search(line)


def ensure_jmrtd_sources(vendor: Path) -> None:
    root = vendor / f"jmrtd-sources-{JMRTD_VERSION}"
    if root.exists():
        return
    url = f"https://repo1.maven.org/maven2/org/jmrtd/jmrtd/{JMRTD_VERSION}/jmrtd-{JMRTD_VERSION}-sources.jar"
    with urllib.request.urlopen(url, timeout=120) as r:
        zipfile.ZipFile(io.BytesIO(r.read())).extractall(root)


def ensure_nfcpr(vendor: Path) -> None:
    root = vendor / "NFCPassportReader-m1"
    if not root.exists():
        subprocess.run(["git", "clone", "-q", "https://github.com/AndyQ/NFCPassportReader.git", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "checkout", "-q", "--detach", NFCPR_COMMIT], check=True)


def step_of(path: str, func: str, line: str) -> str:
    for text in (line, func, path):
        for step, rx in STEP_HINTS:
            if re.search(rx, text):
                return step
    return "OTHER"


def scan(vendor: Path) -> list[dict]:
    items: dict[tuple, dict] = {}
    for lib, (roots, scope, lang) in SCOPE.items():
        name, version = lib.split("@")
        for rel_root in roots:
            root = vendor / rel_root
            for f in sorted(root.rglob("*")):
                rel = f.relative_to(root).as_posix()
                if not f.is_file() or not re.search(scope, rel) or re.search(r"(_test\.go|Test\w*\.\w+|/tests?/)", rel):
                    continue
                func, seen = "", {}
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                for no, line in enumerate(lines, 1):
                    m = re.search(FUNC[lang], line)
                    if m:
                        func, seen = m.group(1), {}
                    s = line.strip()
                    if not s or s.startswith(("//", "*", "/*", "///", "#")):
                        continue
                    kinds = [k for k, rx in PATTERNS[lang] if re.search(rx, line)]
                    if not kinds or not is_decision(kinds, s):
                        continue
                    step = step_of(rel, func, s)
                    if step not in IN_SCOPE_STEPS:
                        continue
                    norm = re.sub(r"\s+", " ", s)
                    seen[norm] = seen.get(norm, 0) + 1
                    key = (name, rel, func, norm, seen[norm])
                    if key in items:
                        items[key]["versions"].append(version)
                        continue
                    items[key] = {
                        "library": name, "versions": [version], "file": rel, "line": no, "function": func,
                        "kinds": "+".join(kinds), "step_hint": step, "code": norm[:200],
                        "context": " | ".join(x.strip() for x in lines[no - 1:no + 5] if x.strip())[:400],
                    }
    out = list(items.values())
    for i, it in enumerate(out, 1):
        it["site_id"] = f"M1-{i:04d}"
        it["versions"] = ",".join(it["versions"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vendor", type=Path, default=Path(__file__).resolve().parents[2] / "_vendor")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "m1-sites.csv")
    args = ap.parse_args()
    ensure_jmrtd_sources(args.vendor)
    ensure_nfcpr(args.vendor)
    rows = scan(args.vendor)
    fields = ["site_id", "library", "versions", "file", "line", "function", "kinds", "step_hint", "code", "context"]
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    by_lib: dict[str, int] = {}
    by_step: dict[str, int] = {}
    for r in rows:
        by_lib[r["library"]] = by_lib.get(r["library"], 0) + 1
        by_step[r["step_hint"]] = by_step.get(r["step_hint"], 0) + 1
    print(f"{len(rows)} sites -> {args.out}")
    print("by library:", by_lib)
    print("by step hint:", by_step)


if __name__ == "__main__":
    main()
