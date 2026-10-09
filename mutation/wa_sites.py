#!/usr/bin/env python3
"""T62 site list (mutation/HELD-OUT-T62.md): decision sites in the main sources of four WebAuthn libraries,
found with the unchanged M1 patterns (mining/m1_sites.py PATTERNS, FUNC, is_decision). The step is the
ceremony: REG, AUTH or BOTH, from the file or function name. Output in the column format of
mining/m1-sites.csv, so mutation/make_mutants.py reads it with --sites.

Usage: python3 mutation/wa_sites.py --vendor ../_vendor --out ../t62/sites.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mining"))
import m1_sites  # noqa: E402

# library -> (source root under VENDOR, language); file paths in the site list are relative to the root
SOURCES = {
    "go-webauthn": ("wa-src/go-webauthn", "go"),
    "java-webauthn-server": ("wa-src/java-webauthn-server/webauthn-server-core/src/main/java", "java"),
    "webauthn4j": ("wa-src/webauthn4j/webauthn4j-core/src/main/java", "java"),
    "fido2-net-lib": ("wa-src/fido2-net-lib/Src/Fido2", "cs"),
}
EXT = {"go": ".go", "java": ".java", "cs": ".cs"}
EXCLUDE = re.compile(r"(_test\.go$|/test/|Test\w*\.\w+$|(^|/)tests?/|(^|/)testing/|(^|/)metadata/|(^|/)Metadata/|(^|/)obj/|(^|/)bin/)")
# Exploratory extension E1 (HELD-OUT-T62.md): Java and C# `if` statements that guard a throw within 3 lines.
E1_IF = re.compile(r"^\s*(\}\s*)?(else\s+)?if\s*\(")
REG = re.compile(r"regist|attestation|MakeNewCredential|CreateCredential|FinishRegistration", re.I)
AUTH = re.compile(r"assert|login|authentic|MakeAssertion|FinishAssertion|ValidateLogin", re.I)


def step(rel: str, func: str) -> str:
    for text in (func, Path(rel).stem):
        r, a = bool(REG.search(text)), bool(AUTH.search(text))
        if r and not a:
            return "REG"
        if a and not r:
            return "AUTH"
    return "BOTH"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", type=Path, default=ROOT.parent / "_vendor")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--extension", choices=["E1"], default=None, help="exploratory extension sites only (X-nnnn)")
    a = ap.parse_args()
    rows = []
    for lib, (rel_root, lang) in SOURCES.items():
        root = a.vendor / rel_root
        for f in sorted(root.rglob("*" + EXT[lang])):
            rel = f.relative_to(root).as_posix()
            if EXCLUDE.search(rel):
                continue
            func = ""
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            for no, line in enumerate(lines, 1):
                m = re.search(m1_sites.FUNC[lang], line)
                if m and m.group(1) not in m1_sites.NOT_FUNCS:
                    func = m.group(1)
                s = line.strip()
                if not s or s.startswith(("//", "*", "/*", "///", "#")):
                    continue
                kinds = [k for k, rx in m1_sites.PATTERNS[lang] if re.search(rx, line)]
                frozen = bool(kinds) and m1_sites.is_decision(kinds, s)
                if a.extension == "E1":
                    if frozen or lang not in ("java", "cs") or not E1_IF.match(line):
                        continue
                    if not any(re.search(r"\bthrow\b", x) for x in lines[no - 1:no + 3]):
                        continue
                    kinds = ["check"]
                elif not frozen:
                    continue
                rows.append({"library": lib, "versions": "x", "file": rel, "line": no, "function": func,
                             "kinds": "+".join(kinds), "step_hint": step(rel, func),
                             "code": re.sub(r"\s+", " ", s)[:200],
                             "context": " | ".join(x.strip() for x in lines[no - 1:no + 5] if x.strip())[:400]})
    for i, r in enumerate(rows, 1):
        r["site_id"] = f"{'X' if a.extension else 'W'}-{i:04d}"
    a.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["site_id", "library", "versions", "file", "line", "function", "kinds", "step_hint", "code", "context"]
    with a.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(len(rows), "sites", dict(Counter((r["library"], r["step_hint"]) for r in rows)))


if __name__ == "__main__":
    main()
