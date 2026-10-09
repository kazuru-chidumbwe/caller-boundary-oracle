#!/usr/bin/env python3
"""Failure-hiding mutants from the M1 site list (mutation/DESIGN.md, part 1 and changes 1 and 2).

Sites: PACE, CA and AA sites of gmrtd (every pin the site occurs in), JMRTD 0.8.9, emrtd-dotnet and
dmrtd. Operators by site kind:

  raise   O1  the throw (or rethrow) statement is replaced by an empty block
  check   O2  the failure check never fires: error test c -> false && (c), success test c -> true || (c)
          O5  the condition is negated
  catch   O3  the catch body is emptied
  status  O4  the failure is not recorded (Go: the error field of the assignment becomes `_`)

Each mutant is one replacement of a line span in one file. Nothing is compiled here; the runner
builds each mutant and records build failures.

Usage: python3 mutation/make_mutants.py --vendor ../_vendor   (writes mutation/mutants.jsonl and mutants.csv)
       python3 mutation/make_mutants.py --vendor ../_vendor --steps SM --out mutation/sm-side
       (design D5 side table: secure-messaging sites, same operators; run on the CA and AA cells)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mining"))
import m1_sites  # noqa: E402

STEPS = {"PACE", "CA", "AA"}
LIBS = {"gmrtd": "go", "jmrtd": "java", "emrtd-dotnet": "cs", "dmrtd": "dart",
        # T62 held-out WebAuthn libraries (mutation/HELD-OUT-T62.md); sites from mutation/wa_sites.py
        "go-webauthn": "go", "java-webauthn-server": "java", "webauthn4j": "java", "fido2-net-lib": "cs"}
SUCCESS_TEST = re.compile(
    r"==\s*(ISO7816\.)?SW_NO_ERROR|==\s*StatusWord\.success|==\s*0x9000\b|(\berr|Err)\s*==\s*nil|"
    r"SW_NO_ERROR\s*==|StatusWord\.success\s*=="
)


def source_root(vendor: Path, library: str, version: str) -> Path:
    if library == "gmrtd":
        return vendor / f"gmrtd-{version}"
    return {"jmrtd": vendor / "jmrtd-sources-0.8.9", "emrtd-dotnet": vendor / "emrtd-dotnet",
            "dmrtd": vendor / "dmrtd",
            "go-webauthn": vendor / "wa-src/go-webauthn",
            "java-webauthn-server": vendor / "wa-src/java-webauthn-server/webauthn-server-core/src/main/java",
            "webauthn4j": vendor / "wa-src/webauthn4j/webauthn4j-core/src/main/java",
            "fido2-net-lib": vendor / "wa-src/fido2-net-lib/Src/Fido2"}[library]


def occurrences(lines: list[str], lang: str) -> dict[int, tuple[str, str, int]]:
    """Line number -> (function, normalised line, occurrence in function), as m1_sites counts them."""
    out, func, seen = {}, "", {}
    for no, line in enumerate(lines, 1):
        m = re.search(m1_sites.FUNC[lang], line)
        if m and m.group(1) not in m1_sites.NOT_FUNCS:
            func, seen = m.group(1), {}
        s = line.strip()
        if not s:
            continue
        norm = re.sub(r"\s+", " ", s)
        seen[norm] = seen.get(norm, 0) + 1
        out[no] = (func, norm, seen[norm])
    return out


def locate(site: dict, vendor: Path, version: str, first: str) -> int | None:
    """Line of the site in another gmrtd pin: same function, same normalised line, same occurrence."""
    lang = LIBS[site["library"]]
    ref = (source_root(vendor, site["library"], first) / site["file"]).read_text(encoding="utf-8", errors="replace").splitlines()
    key = occurrences(ref, lang).get(int(site["line"]))
    path = source_root(vendor, site["library"], version) / site["file"]
    if key is None or not path.exists():
        return None
    for no, k in occurrences(path.read_text(encoding="utf-8", errors="replace").splitlines(), lang).items():
        if k == key:
            return no
    return None


def scan_code(text: str, start: int, opener: str, closer: str) -> int | None:
    """Index just after the bracket that closes the one at text[start] (strings and comments skipped)."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "\"'`":
            q = c
            i += 1
            while i < n and text[i] != q:
                i += 2 if text[i] == "\\" else 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def statement_end(text: str, start: int) -> int | None:
    """Index just after the ';' that ends the statement starting at text[start]."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "\"'`":
            q = c
            i += 1
            while i < n and text[i] != q:
                i += 2 if text[i] == "\\" else 1
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth < 0:
                return None
        elif c == ";" and depth == 0:
            return i + 1
        i += 1
    return None


def line_offsets(text: str) -> list[int]:
    offs, pos = [0], 0
    for line in text.split("\n"):
        pos += len(line) + 1
        offs.append(pos)
    return offs


def keyword_at(text: str, start: int, end: int, word: str) -> int | None:
    m = re.compile(r"(?<![\w.])" + word + r"\b").search(text, start, end)
    return m.start() if m else None


def op_raise(text: str, lo: int, hi: int):
    pos = keyword_at(text, lo, hi, "rethrow") or keyword_at(text, lo, hi, "throw")
    if pos is None:
        return None, "no throw on the line"
    before = text[lo:pos].rstrip()
    if before.endswith(("??", "=>", "?", ":", "(", ",", "=")):
        return None, "throw used as an expression"
    end = statement_end(text, pos)
    if end is None:
        return None, "statement end not found"
    return (pos, end, "{}"), None


def condition_span(text: str, lo: int, hi: int, lang: str):
    pos = keyword_at(text, lo, hi, "if")
    if pos is None:
        return None
    if lang == "go":
        brace = text.find("{", pos)
        line_end = text.find("\n", pos)
        if brace < 0 or (0 <= line_end < brace):
            return None
        head = text[pos + 2:brace]
        depth, cut = 0, None
        for k, c in enumerate(head):
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == ";" and depth == 0:
                cut = k
        cstart = pos + 2 + (cut + 1 if cut is not None else 0)
        while text[cstart] == " ":
            cstart += 1
        cend = brace
        while text[cend - 1] == " ":
            cend -= 1
        return cstart, cend
    paren = text.find("(", pos)
    if paren < 0:
        return None
    close = scan_code(text, paren, "(", ")")
    if close is None:
        return None
    return paren + 1, close - 1


def op_check(text: str, lo: int, hi: int, lang: str, op: str):
    span = condition_span(text, lo, hi, lang)
    if span is None:
        return None, "condition not found"
    a, b = span
    cond = text[a:b]
    if op == "O5":
        return (a, b, f"!({cond})"), None
    if SUCCESS_TEST.search(cond):
        return (a, b, f"true || ({cond})"), None
    return (a, b, f"false && ({cond})"), None


def op_catch(text: str, lo: int, hi: int):
    pos = keyword_at(text, lo, hi, "catch")
    if pos is None:
        pos = keyword_at(text, lo, hi, "on")
    if pos is None:
        return None, "no catch on the line"
    i = pos
    while i < len(text) and text[i] != "{":
        if text[i] == "(":
            j = scan_code(text, i, "(", ")")
            if j is None:
                return None, "catch clause not closed"
            i = j
            continue
        if text[i] == ";":
            return None, "no catch block"
        i += 1
    end = scan_code(text, i, "{", "}")
    if end is None:
        return None, "catch block not closed"
    return (i + 1, end - 1, ""), None


def op_status_write(text: str, lo: int, hi: int, lang: str):
    """O4: the failure is no longer recorded. Go only: the field that receives the error, in a
    single or multiple assignment, is replaced by the blank identifier."""
    if lang != "go":
        return None, "status write not mutated outside Go"
    line = text[lo:hi]
    eq = re.search(r"(?<![=!<>:])=(?!=)", line)
    if eq is None:
        return None, "assignment not found"
    targets = line[:eq.start()]
    m = None
    for m in re.finditer(r"[\w.\[\]()*]+Err\b", targets):
        pass
    if m is None:
        return None, "no error field among the assignment targets"
    return (lo + m.start(), lo + m.end(), "_"), None


def mutants_for(site: dict, version: str, line: int, path: Path) -> list[dict]:
    lang = LIBS[site["library"]]
    text = path.read_text(encoding="utf-8", errors="replace")
    offs = line_offsets(text)
    lo, hi = offs[line - 1], offs[line] - 1
    kinds = site["kinds"].split("+")
    ops = []
    if "raise" in kinds:
        ops.append("O1")
    if "check" in kinds:
        ops += ["O2", "O5"]
    if "catch" in kinds:
        ops.append("O3")
    if "status_write" in kinds:
        ops.append("O4")
    out = []
    for op in ops:
        if op == "O1":
            edit, why = op_raise(text, lo, hi)
        elif op == "O3":
            edit, why = op_catch(text, lo, hi)
        elif op == "O4":
            edit, why = op_status_write(text, lo, hi, lang)
        else:
            edit, why = op_check(text, lo, hi, lang, op)
        mid = f"{site['site_id']}-{version}-{op}"
        rec = {"mutant_id": mid, "site_id": site["site_id"], "library": site["library"], "version": version,
               "step": site["step_hint"], "operator": op, "file": site["file"], "line": line}
        if edit is None:
            out.append(rec | {"status": "not_applied", "reason": why})
            continue
        a, b, repl = edit
        if text[a:b] == repl:
            out.append(rec | {"status": "not_applied", "reason": "no change"})
            continue
        out.append(rec | {"status": "ok", "start": a, "end": b, "original": text[a:b], "replacement": repl,
                          "end_line": text.count("\n", 0, b) + 1})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vendor", type=Path, default=ROOT.parent / "_vendor")
    ap.add_argument("--sites", type=Path, default=ROOT / "mining" / "m1-sites.csv")
    ap.add_argument("--steps", default=",".join(sorted(STEPS)), help="comma-separated step hints (default PACE,CA,AA)")
    ap.add_argument("--out", type=Path, default=ROOT / "mutation", help="directory for mutants.jsonl and mutants.csv")
    a = ap.parse_args()
    steps = set(a.steps.split(","))
    a.out.mkdir(parents=True, exist_ok=True)
    sites = [s for s in csv.DictReader(a.sites.open(encoding="utf-8", newline=""))
             if s["library"] in LIBS and s["step_hint"] in steps]
    records = []
    for s in sites:
        versions = s["versions"].split(",") if s["library"] == "gmrtd" else ["x"]
        for v in dict.fromkeys(versions):
            line = int(s["line"]) if v == versions[0] else (locate(s, a.vendor, v, versions[0]) if s["library"] == "gmrtd" else None)
            if line is None:
                records.append({"mutant_id": f"{s['site_id']}-{v}", "site_id": s["site_id"], "library": s["library"],
                                "version": v, "status": "not_located", "reason": "site not found in this pin"})
                continue
            path = source_root(a.vendor, s["library"], v) / s["file"]
            records += mutants_for(s, v, line, path)
    out = a.out / "mutants.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    fields = ["mutant_id", "site_id", "library", "version", "step", "operator", "file", "line", "status", "reason"]
    with (a.out / "mutants.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)
    counts: dict[tuple, int] = {}
    for r in records:
        k = (r["library"], r.get("operator", "-"), r["status"])
        counts[k] = counts.get(k, 0) + 1
    print(f"{len(sites)} sites -> {len(records)} records -> {out}")
    for k in sorted(counts):
        print("  ", *k, counts[k])


if __name__ == "__main__":
    main()
