#!/usr/bin/env python3
"""M1 batch 2 item list: failure-handling sites in the verification code of each WebAuthn library.

Same unit and rules as batch 1 (mining/m1_sites.py): a site is a line where the library decides what to do with a
failed verification step (an error check, a catch, a throw or raise, or a write of a failure value). Batch 2
extends batch 1 only by file scope and by the same pattern families written for two new languages (Python,
TypeScript) and two library idioms (PROTOCOL.md, change 4):

- Java: the check helpers that throw (java-webauthn-server's `assertTrue`/`assertFalse`, `Assert.isTrue`) count
  as raise.
- Go: a return that builds a new error (`fmt.Errorf`, `errors.New`, a package error value `Err...`) counts as
  raise; a return that passes `err` on is context of its `if err != nil` check, as in batch 1.

Steps in scope are the relying-party checks the WebAuthn fault model injects (webauthn/FAULTS.md): client data
type, challenge, origin, RP ID hash, the UP/UV/BE/BS flags, the assertion and packed attestation signatures,
and the signature counter (W3C WebAuthn Level 3, 7.1 steps 7 to 22 and 7.2 steps 10 to 23). Attestation trust
(7.1 step 24), the other attestation formats, metadata and option generation are out of scope, as in the
fault model.

Sources are fetched at the pinned driver versions (git tags resolved to the commits below). Site IDs continue
after the highest ID in the batch 1 list. Usage:

  python3 mining/m1_sites_b2.py --vendor ../_vendor --batch1 mining/m1-sites.csv --out mining/m1-sites-b2.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from pathlib import Path

import m1_sites as b1

# library@version -> (git URL, commit for that tag, source root inside the checkout, files in scope, language)
SOURCES = {
    "py_webauthn@3.0.1": ("https://github.com/duo-labs/py_webauthn", "d72e0f53cb6684fdd2f178bae83aeab8bda64665",
        "webauthn",
        r"^(registration/verify_registration_response|authentication/verify_authentication_response"
        r"|registration/formats/packed|helpers/(verify_signature|parse_backup_flags))\.py$", "python"),
    "simplewebauthn-server@14.0.3": ("https://github.com/MasterKale/SimpleWebAuthn", "787ca8209e39bc5f868a6a42f6b98a1bc1c06206",
        "packages/server/src",
        r"^(registration/verifyRegistrationResponse|authentication/verifyAuthenticationResponse"
        r"|registration/verifications/verifyAttestationPacked|helpers/(verifySignature|parseBackupFlags|matchExpectedRPID))\.ts$", "ts"),
    "go-webauthn@0.18.2": ("https://github.com/go-webauthn/webauthn", "a4c6fc6a4399bcd1ba982c116189f1598d9d5eec",
        "",
        r"^(protocol/(assertion|attestation|attestation_packed|authenticator|client|credential|signature)"
        r"|webauthn/(login|registration))\.go$", "go"),
    "java-webauthn-server@2.10.0": ("https://github.com/Yubico/java-webauthn-server", "0e2db1aec833ec423c360145dfcd9a497c6387dd",
        "webauthn-server-core/src/main/java",
        r"^com/yubico/webauthn/(FinishAssertionSteps|FinishRegistrationSteps|PackedAttestationStatementVerifier"
        r"|OriginMatcher|Crypto|RelyingParty|RelyingPartyV2)\.java$", "java"),
    "webauthn4j@0.31.11.RELEASE": ("https://github.com/webauthn4j/webauthn4j", "fb63b0d32a4c4be5ac89c3735e67025ad439b824",
        "webauthn4j-core/src/main/java",
        r"^com/webauthn4j/(WebAuthn(Authentication|Registration)?Manager|verifier/(AuthenticationDataVerifier"
        r"|CoreAuthenticationDataVerifier|CoreRegistrationDataVerifier|RegistrationDataVerifier|AttestationVerifier"
        r"|OriginVerifierImpl|DefaultCoreMaliciousCounterValueHandler|DefaultMaliciousCounterValueHandler"
        r"|internal/(AssertionSignatureVerifier|BEBSFlagsVerifier|BEFlagVerifier|ChallengeVerifier|RpIdHashVerifier"
        r"|UPUVFlagsVerifier)|attestation/statement/(AbstractStatementVerifier|packed/PackedAttestationStatementVerifier)))\.java$", "java"),
    "fido2-net-lib@4.2.0": ("https://github.com/passwordless-lib/fido2-net-lib", "9218d55635cc402080cf9931bcfc23cc7318b082",
        "Src/Fido2",
        r"^(AuthenticatorAssertionResponse|AuthenticatorAttestationResponse|AuthenticatorResponse|Fido2"
        r"|AttestationFormat/(Packed|AttestationVerifier)|Objects/AuthenticatorData)\.cs$", "cs"),
}

PATTERNS = dict(b1.PATTERNS)
PATTERNS["java"] = b1.PATTERNS["java"] + [("raise", r"\b(assertTrue|assertFalse|Assert\.isTrue|Assert\.isFalse)\s*\(")]
PATTERNS["go"] = [(k, rx) for k, rx in b1.PATTERNS["go"] if k != "return_error"] + [
    ("raise", r"\breturn\b.*\b(fmt\.Errorf|errors\.New|Err[A-Z]\w*)\b"),
    ("return_error", r"\breturn\b.*\berr\b"),
]
PATTERNS["python"] = [
    ("catch", r"^\s*except\b"),
    ("raise", r"\braise\b"),
    ("status_write", r"\b\w*(verified|valid|error|failed|status)\w*\s*=[^=]"),
    ("log", r"\b(log|logger|logging)\.\w+\("),
    ("check", r"\bif\b.*\b(is\s+None|is\s+not\s+None)\b.*\b(err|error|result)\w*"),
]
PATTERNS["ts"] = [
    ("catch", r"\bcatch\b"),
    ("raise", r"\bthrow\b"),
    ("status_write", r"\b\w*(verified|Verified|error|Error|status|Status|failed|Failed)\w*\s*=[^=>]"),
    ("log", r"\blog\w*\(|\bconsole\.\w+\("),
    ("check", r"\bif\s*\(.*\b(err|error|result)\w*\b"),
]

FUNC = dict(b1.FUNC)
FUNC["python"] = r"^\s*(?:async\s+)?def\s+(\w+)"
FUNC["ts"] = (r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s*\*?\s*(\w+)"
              r"|(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|\w+)\s*=>)")

# Step names follow webauthn/FAULTS.md. Order matters: the first match wins.
STEP_HINTS = [
    ("CNT", r"sign.?count|signCount|SignCount|sign_count|[Cc]ounter"),
    ("SIG", r"[Ss]ignature|verify_signature|verifySignature|attStmt|AttestationStatement|attestation_statement|\bsig\b"),
    ("FLAGS", r"user.?present|userPresent|UserPresent|user_present|\bUP\b|\.up\b|user.?verif|UserVerif|user_verif"
              r"|\bUV\b|\.uv\b|backup.?(eligib|state)|Backup(Eligible|State)|backup_(eligible|state)|\bBE\b|\bBS\b"
              r"|\.be\b|\.bs\b|[Ff]lags"),
    ("RPID", r"rpIdHash|RpIdHash|rp_id_hash|RPIDHash|rpId|RpId|rp_id|RPID|RpID"),
    ("ORIG", r"[Oo]rigin"),
    ("CHAL", r"[Cc]hallenge"),
    ("TYPE", r"webauthn\.(create|get)|[Cc]lient[Dd]ata\w*\.[Tt]ype|client_data\.type|[Cc]eremony|\bctype\b"),
]
IN_SCOPE_STEPS = {s for s, _ in STEP_HINTS}


def first_step(texts: tuple[str, ...]) -> str:
    for text in texts:
        for step, rx in STEP_HINTS:
            if re.search(rx, text):
                return step
    return "OTHER"


def step_of(path: str, func: str, line: str, window: str) -> str:
    step = first_step((line, func, path))
    if step in IN_SCOPE_STEPS:
        return step
    near = first_step((window,))
    return near if near in IN_SCOPE_STEPS else step


def ensure_sources(vendor: Path) -> None:
    for lib, (url, commit, *_rest) in SOURCES.items():
        root = vendor / ("m1b2-" + lib.split("@")[0])
        if not root.exists():
            subprocess.run(["git", "clone", "-q", url, str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "checkout", "-q", "--detach", commit], check=True)


def scan(vendor: Path) -> list[dict]:
    items: dict[tuple, dict] = {}
    for lib, (_url, _commit, src, scope, lang) in SOURCES.items():
        name, version = lib.split("@")
        root = vendor / ("m1b2-" + name) / src
        for f in sorted(root.rglob("*")):
            rel = f.relative_to(root).as_posix()
            if not f.is_file() or not re.search(scope, rel) or re.search(r"(_test\.go|Test\w*\.\w+|/tests?/|\.test\.ts$)", rel):
                continue
            func, seen = "", {}
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            for no, line in enumerate(lines, 1):
                m = re.search(FUNC[lang], line)
                if m:
                    g = next((x for x in m.groups() if x), None)
                    if g and g not in b1.NOT_FUNCS:
                        func, seen = g, {}
                s = line.strip()
                if not s or s.startswith(("//", "*", "/*", "///", "#")):
                    continue
                kinds = [k for k, rx in PATTERNS[lang] if re.search(rx, line)]
                if not kinds or not b1.is_decision(kinds, s):
                    continue
                window = " ".join(x.strip() for x in lines[max(0, no - 4):no + 5])
                step = step_of(rel, func, s, window)
                if step not in IN_SCOPE_STEPS:
                    continue
                norm = re.sub(r"\s+", " ", s)
                seen[norm] = seen.get(norm, 0) + 1
                key = (name, rel, func, norm, seen[norm])
                items[key] = {
                    "library": name, "versions": version, "file": rel, "line": no, "function": func,
                    "kinds": "+".join(kinds), "step_hint": step, "code": norm[:200],
                    "context": " | ".join(x.strip() for x in lines[no - 1:no + 5] if x.strip())[:400],
                }
    return list(items.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vendor", type=Path, default=Path(__file__).resolve().parents[2] / "_vendor")
    ap.add_argument("--batch1", type=Path, default=Path(__file__).resolve().parent / "m1-sites.csv")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "m1-sites-b2.csv")
    ap.add_argument("--no-fetch", action="store_true", help="use the checkouts already in --vendor")
    args = ap.parse_args()
    if not args.no_fetch:
        ensure_sources(args.vendor)
    rows = scan(args.vendor)
    with args.batch1.open(encoding="utf-8", newline="") as f:
        start = max(int(r["site_id"].split("-")[1]) for r in csv.DictReader(f))
    rows.sort(key=lambda r: (r["library"], r["file"], r["line"]))
    for i, r in enumerate(rows, start + 1):
        r["site_id"] = f"M1-{i:04d}"
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
    print(f"{len(rows)} sites -> {args.out} (IDs from M1-{start + 1:04d})")
    print("by library:", by_lib)
    print("by step hint:", by_step)


if __name__ == "__main__":
    main()
