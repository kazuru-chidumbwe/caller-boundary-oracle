#!/usr/bin/env python3
"""WebAuthn fault peer: a deterministic software authenticator that injects one fault per case.

For each case in CASES it writes three files into <out>/<case>/:

  options.json   what the relying party issued and stored: RP ID, origin, challenge, whether user
                 verification is required, and (for authentication) the stored credential
  response.json  the PublicKeyCredential in the WebAuthn Level 3 JSON serialisation
                 (RegistrationResponseJSON or AuthenticationResponseJSON)
  report.json    the delivery report: case, ceremony, fault, whether a fault was injected, and the
                 SHA-256 of response.json exactly as written

The key, the credential ID and the challenges are derived from fixed seeds and ECDSA signing is
deterministic (RFC 6979), so the same version of this file always writes the same bytes. Fault
IDs and the specification steps they violate are listed in webauthn/FAULTS.md.

Usage: python3 webauthn/authenticator.py --out logs/webauthn/cases [--list]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
from pathlib import Path

import cbor2
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

RP_ID = "rp.cbo.test"
ORIGIN = "https://rp.cbo.test"
OTHER_RP_ID = "other.cbo.test"
OTHER_ORIGIN = "https://other.cbo.test"
USER_ID = b"cbo-user-0001"
OTHER_USER_ID = b"cbo-user-0002"
PORT_ORIGIN = "https://rp.cbo.test:8443"
ES256, RS256 = -7, -257
STORED_COUNT = 10
AAGUID = bytes(16)

UP, UV, BE, BS, AT = 0x01, 0x04, 0x08, 0x10, 0x40

# (case, ceremony, fault or None, attestation format)
CASES = [
    ("R-OK-NONE", "registration", None, "none"),
    ("R-OK-PACKED", "registration", None, "packed"),
    ("R-TYPE", "registration", "R-TYPE", "none"),
    ("R-CHAL", "registration", "R-CHAL", "none"),
    ("R-ORIG", "registration", "R-ORIG", "none"),
    ("R-RPID", "registration", "R-RPID", "none"),
    ("R-UP", "registration", "R-UP", "none"),
    ("R-UV", "registration", "R-UV", "none"),
    ("R-BS", "registration", "R-BS", "none"),
    ("R-ASIG", "registration", "R-ASIG", "packed"),
    ("A-OK", "authentication", None, None),
    ("A-TYPE", "authentication", "A-TYPE", None),
    ("A-CHAL", "authentication", "A-CHAL", None),
    ("A-ORIG", "authentication", "A-ORIG", None),
    ("A-RPID", "authentication", "A-RPID", None),
    ("A-UP", "authentication", "A-UP", None),
    ("A-UV", "authentication", "A-UV", None),
    ("A-BS", "authentication", "A-BS", None),
    ("A-SIG", "authentication", "A-SIG", None),
    ("A-CNT", "authentication", "A-CNT", None),
    # held-out cases (HELD-OUT-DESIGN.md, 8 Oct 2026); never run during development
    ("R-UPUV", "registration", "R-UPUV", "none"),
    ("R-ORIGPORT", "registration", "R-ORIGPORT", "none"),
    ("R-XORIG", "registration", "R-XORIG", "none"),
    ("R-NONESTMT", "registration", "R-NONESTMT", "none"),
    ("R-ALG", "registration", "R-ALG", "none"),
    ("A-UPUV", "authentication", "A-UPUV", None),
    ("A-ORIGPORT", "authentication", "A-ORIGPORT", None),
    ("A-XORIG", "authentication", "A-XORIG", None),
    ("A-UH", "authentication", "A-UH", None),
    ("A-CRED", "authentication", "A-CRED", None),
    ("A-CNTEQ", "authentication", "A-CNTEQ", None),
]


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def seeded(label: str, n: int = 32) -> bytes:
    return hashlib.sha256(b"cbo-webauthn/" + label.encode()).digest()[:n]


KEY = ec.derive_private_key(int.from_bytes(seeded("credential-key"), "big") % (2**255), ec.SECP256R1())
CRED_ID = seeded("credential-id", 16)


def sign(data: bytes) -> bytes:
    return KEY.sign(data, ec.ECDSA(hashes.SHA256(), deterministic_signing=True))


def cose_key() -> bytes:
    n = KEY.public_key().public_numbers()
    return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")}, canonical=True)


def spki() -> bytes:
    return KEY.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def client_data(ceremony: str, challenge: bytes, fault: str | None) -> bytes:
    typ = "webauthn.create" if ceremony == "registration" else "webauthn.get"
    if fault in ("R-TYPE", "A-TYPE"):
        typ = "webauthn.get" if ceremony == "registration" else "webauthn.create"
    if fault in ("R-CHAL", "A-CHAL"):
        challenge = seeded("wrong-challenge")
    origin = OTHER_ORIGIN if fault in ("R-ORIG", "A-ORIG") else ORIGIN
    if fault in ("R-ORIGPORT", "A-ORIGPORT"):
        origin = PORT_ORIGIN
    cd = {"type": typ, "challenge": b64u(challenge), "origin": origin, "crossOrigin": False}
    if fault in ("R-XORIG", "A-XORIG"):  # embedded in a cross-origin iframe the RP did not expect
        cd["crossOrigin"] = True
        cd["topOrigin"] = OTHER_ORIGIN
    return json.dumps(cd, separators=(",", ":")).encode()


def auth_data(ceremony: str, fault: str | None) -> bytes:
    rp = OTHER_RP_ID if fault in ("R-RPID", "A-RPID") else RP_ID
    flags = UP | UV
    if fault in ("R-UP", "A-UP"):
        flags &= ~UP
    if fault in ("R-UV", "A-UV"):
        flags &= ~UV
    if fault in ("R-BS", "A-BS"):
        flags |= BS
    if fault in ("R-UPUV", "A-UPUV"):
        flags = UV
    if ceremony == "registration":
        flags |= AT
        count = 0
    else:
        count = STORED_COUNT - 5 if fault == "A-CNT" else STORED_COUNT if fault == "A-CNTEQ" else STORED_COUNT + 1
    out = hashlib.sha256(rp.encode()).digest() + bytes([flags]) + struct.pack(">I", count)
    if ceremony == "registration":
        out += AAGUID + struct.pack(">H", len(CRED_ID)) + CRED_ID + cose_key()
    return out


def build(case: str, ceremony: str, fault: str | None, fmt: str | None) -> tuple[dict, dict]:
    challenge = seeded("challenge/" + case)
    cdata = client_data(ceremony, challenge, fault)
    adata = auth_data(ceremony, fault)
    signed = adata + hashlib.sha256(cdata).digest()
    if fault in ("R-ASIG", "A-SIG"):
        # a well-formed signature by the right key over different bytes
        signed = signed[:-1] + bytes([signed[-1] ^ 0x01])
    options = {"rpId": RP_ID, "rpName": "CBO test RP", "origin": ORIGIN, "challenge": b64u(challenge),
               "userId": b64u(USER_ID), "userName": "cbo-user", "requireUserVerification": True,
               "pubKeyCredParams": [RS256] if fault == "R-ALG" else [ES256]}
    if ceremony == "registration":
        stmt = {} if fmt == "none" else {"alg": -7, "sig": sign(signed)}
        if fault == "R-NONESTMT":  # fmt none with a non-empty statement
            stmt = {"alg": -7, "sig": sign(signed)}
        att = cbor2.dumps({"fmt": fmt, "attStmt": stmt, "authData": adata}, canonical=True)
        options["attestation"] = "none" if fmt == "none" else "direct"
        response = {"id": b64u(CRED_ID), "rawId": b64u(CRED_ID), "type": "public-key",
                    "response": {"clientDataJSON": b64u(cdata), "authenticatorData": b64u(adata),
                                 "transports": ["usb"], "publicKeyAlgorithm": -7, "publicKey": b64u(spki()),
                                 "attestationObject": b64u(att)},
                    "clientExtensionResults": {}, "authenticatorAttachment": "cross-platform"}
    else:
        options["credential"] = {"id": b64u(CRED_ID), "publicKeyCose": b64u(cose_key()), "publicKeySpki": b64u(spki()),
                                 "alg": -7, "signCount": STORED_COUNT, "userId": b64u(USER_ID)}
        options["allowCredentials"] = [b64u(seeded("other-credential-id", 16)) if fault == "A-CRED" else b64u(CRED_ID)]
        response = {"id": b64u(CRED_ID), "rawId": b64u(CRED_ID), "type": "public-key",
                    "response": {"clientDataJSON": b64u(cdata), "authenticatorData": b64u(adata),
                                 "signature": b64u(sign(signed)),
                                 "userHandle": b64u(OTHER_USER_ID if fault == "A-UH" else USER_ID)},
                    "clientExtensionResults": {}, "authenticatorAttachment": "cross-platform"}
    return options, response


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/webauthn/cases")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for c in CASES:
            print(c[0])
        return
    out = Path(a.out)
    me = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for case, ceremony, fault, fmt in CASES:
        options, response = build(case, ceremony, fault, fmt)
        d = out / case
        d.mkdir(parents=True, exist_ok=True)
        (d / "options.json").write_text(json.dumps(options, indent=2) + "\n", encoding="utf-8")
        body = (json.dumps(response, indent=2) + "\n").encode()
        (d / "response.json").write_bytes(body)
        report = {"case": case, "ceremony": ceremony, "fault": fault, "injected": fault is not None,
                  "response_sha256": hashlib.sha256(body).hexdigest(), "peer_sha256": me}
        (d / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{len(CASES)} cases written to {out}")


if __name__ == "__main__":
    main()
