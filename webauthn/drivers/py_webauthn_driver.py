#!/usr/bin/env python3
"""py_webauthn driver: verify one fault-peer case the way an integrator would and print the raw record.

Reads <case>/options.json and <case>/response.json, calls verify_registration_response or
verify_authentication_response with the options the relying party issued (user verification
required), and prints one JSON object: whether the call raised, the exception type and message,
the fields of the returned result, and the SHA-256 of the response bytes that were passed in.
Observations are derived from this record by webauthn/run.py; this file does not classify.

Usage: python3 webauthn/drivers/py_webauthn_driver.py <case-dir>
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import webauthn
from webauthn.helpers import parse_authentication_credential_json, parse_registration_credential_json
from webauthn.helpers.cose import COSEAlgorithmIdentifier


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def val(x) -> str:
    return str(getattr(x, "value", x))


def main() -> None:
    d = Path(sys.argv[1])
    opts = json.loads((d / "options.json").read_text(encoding="utf-8"))
    body = (d / "response.json").read_bytes()
    rec = {"library": "py_webauthn", "version": webauthn.__version__, "passed_sha256": hashlib.sha256(body).hexdigest(),
           "returned_error": False, "error_type": None, "error": None, "fields": {}}
    try:
        if "credential" not in opts:
            res = webauthn.verify_registration_response(
                credential=parse_registration_credential_json(body.decode()),
                expected_challenge=b64d(opts["challenge"]), expected_origin=opts["origin"],
                expected_rp_id=opts["rpId"], require_user_verification=opts["requireUserVerification"],
                supported_pub_key_algs=[COSEAlgorithmIdentifier(a) for a in opts.get("pubKeyCredParams", [-7])])
            rec["fields"] = {"user_verified": res.user_verified, "credential_backed_up": res.credential_backed_up,
                             "credential_device_type": val(res.credential_device_type),
                             "fmt": val(res.fmt)}
        else:
            c = opts["credential"]
            res = webauthn.verify_authentication_response(
                credential=parse_authentication_credential_json(body.decode()),
                expected_challenge=b64d(opts["challenge"]), expected_origin=opts["origin"],
                expected_rp_id=opts["rpId"], credential_public_key=b64d(c["publicKeyCose"]),
                credential_current_sign_count=c["signCount"], require_user_verification=opts["requireUserVerification"])
            rec["fields"] = {"user_verified": res.user_verified, "credential_backed_up": res.credential_backed_up,
                             "credential_device_type": val(res.credential_device_type),
                             "new_sign_count": res.new_sign_count}
    except Exception as e:  # the integrator's view: any exception from verify is a refusal
        rec.update(returned_error=True, error_type=type(e).__name__, error=str(e)[:300])
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
