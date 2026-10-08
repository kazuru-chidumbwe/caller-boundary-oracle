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
    # Added 8 Oct 2026 before any item was coded (PROTOCOL.md, change 2): passauf v0.2.0, the sixth library.
    "passauf@48b7cc7": (["passauf"], r"^src/(session|iso7816|icao9303|secure_messaging|smartcard_abstractions|pace/[^/]+)\.rs$", "rust"),
}

PATTERNS = {
    "go": [
        ("check", r"\bif\s+.*(err|Err)\s*[!=]=\s*nil"),
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
    # Rust has no exceptions: a failure is decided by matching on Err or None, by propagating it with `?` or
    # `return Err(..)`, or by aborting with panic!, expect or unwrap. Each of these is a decision point.
    "rust": [
        ("check", r"\b(Err|None)\s*(\([^)]*\))?\s*=>|\bif\s+let\s+(Err|None)\b|\.is_(err|none)\(\)"),
        ("raise", r"\bpanic!\(|\.expect\(|\.unwrap\(\)|\breturn\s+Err\(|\?\s*[;,)]|\?$"),
        ("status_write", r"\b\w*(warnings|status|error|failed|Failed)\w*\s*(=[^=>]|\.push\()"),
        ("log", r"\b(warn|error|info|debug)!\("),
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
    "rust": r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)",
}
STEP_HINTS = [
    ("PACE", r"pace|PACE|Pace|mapNonce|GeneralAuthenticate|general_authenticate"),
    ("CA", r"chipauth|ChipAuth|chipAuth|ChipAuthentication|CAProtocol|doCA|\bCA\b|EACCA|eacCA|SetATIntAuth"),
    ("AA", r"activeauth|ActiveAuth|activeAuth|InternalAuthenticate|internalAuthenticate|AAProtocol|doAA"),
    ("BAC", r"\bbac\b|BAC|Bac|ExternalAuthenticate|MutualAuth|mutualAuth"),
    ("SM", r"secure.?messag|SecureMessag|\bsm\b|unprotect|unwrap|SMWrapper|SecureMessagingWrapper"),
    ("PA", r"passiveauth|PassiveAuth|SOD|verifySignature"),
    ("FILE", r"ReadBinary|readBinary|SelectEF|selectEF|readFile|ReadFile|getInputStream"),
]


IN_SCOPE_STEPS = {"PACE", "BAC", "CA", "AA", "SM"}
# A status write is a decision site when it records a failure value, or assigns to a field that
# holds an error (Go: `Session.PaceErr = ...`, also inside a multiple assignment).
FAILURE_VALUE = re.compile(r"fail|\bfalse\b|\.failed\b|\berr|\bnil\b|\bnull\b|Err\s*(=[^=]|,)", re.I)
SUCCESS_VALUE = re.compile(r"=\s*(true|\.success)\b")


def is_decision(kinds: list[str], line: str) -> bool:
    if {"check", "catch", "raise"} & set(kinds):
        return True
    if "status_write" in kinds and re.search(r"warnings\.push\(", line):
        return True  # passauf: a message pushed onto DocumentRead.warnings, the status field the caller gets
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


# Words the function patterns can capture although they are not function names.
NOT_FUNCS = {"if", "for", "foreach", "while", "switch", "catch", "when", "using", "lock", "return", "new",
             "else", "do", "try", "throw", "await", "sizeof", "typeof", "nameof", "base", "this", "on"}


def first_step(texts: tuple[str, ...]) -> str:
    for text in texts:
        for step, rx in STEP_HINTS:
            if re.search(rx, text):
                return step
    return "OTHER"


def step_of(path: str, func: str, line: str, window: str = "") -> str:
    """Step hint from the line, the function and the path. Only when that gives no step in scope
    are the lines around the site read as well (a handler often names the step only in its body,
    e.g. "PACE failed ... falling back to BAC"), so sites listed before keep their step."""
    step = first_step((line, func, path))
    if step in IN_SCOPE_STEPS or not window:
        return step
    near = first_step((window,))
    return near if near in IN_SCOPE_STEPS else step


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
                    # Rust keeps unit tests in an inline module; other languages' tests are excluded by path.
                    if lang == "rust" and re.match(r"\s*#\[cfg\(test\)\]", line):
                        break
                    m = re.search(FUNC[lang], line)
                    if m and m.group(1) not in NOT_FUNCS:
                        func, seen = m.group(1), {}
                    s = line.strip()
                    if not s or s.startswith(("//", "*", "/*", "///", "#")):
                        continue
                    kinds = [k for k, rx in PATTERNS[lang] if re.search(rx, line)]
                    if not kinds or not is_decision(kinds, s):
                        continue
                    window = " ".join(x.strip() for x in lines[max(0, no - 4):no + 5])
                    step = step_of(rel, func, s, window)
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
    for it in out:
        it["versions"] = ",".join(it["versions"])
    return out


def assign_ids(rows: list[dict], previous: Path) -> tuple[int, list[str]]:
    """Keep the ID of every site already in the published list (matched on library, file, line
    and code); number new sites after the highest existing ID. Returns (new count, dropped IDs)."""
    old: dict[tuple, str] = {}
    if previous.exists():
        with previous.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                old[(r["library"], r["file"], r["line"], r["code"])] = r["site_id"]
    nxt = max((int(v.split("-")[1]) for v in old.values()), default=0)
    used, new = set(), 0
    for r in rows:
        sid = old.get((r["library"], r["file"], str(r["line"]), r["code"]))
        if sid is None:
            nxt += 1
            new += 1
            sid = f"M1-{nxt:04d}"
        r["site_id"] = sid
        used.add(sid)
    rows.sort(key=lambda r: r["site_id"])
    return new, sorted(set(old.values()) - used)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vendor", type=Path, default=Path(__file__).resolve().parents[2] / "_vendor")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "m1-sites.csv")
    args = ap.parse_args()
    ensure_jmrtd_sources(args.vendor)
    ensure_nfcpr(args.vendor)
    rows = scan(args.vendor)
    new, dropped = assign_ids(rows, args.out)
    print(f"kept IDs: {len(rows) - new}, new sites: {new}, dropped IDs: {dropped}")
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
