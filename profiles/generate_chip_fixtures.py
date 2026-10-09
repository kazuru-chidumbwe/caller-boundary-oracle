#!/usr/bin/env python3
"""Build EF.SOD fixtures whose hash lists match the DG14/DG15 the simulated chip serves.

gmrtd's ReadDocument only reads data groups listed in EF.SOD, so CA and AA are reached
through the shipped call path only when the SOD lists DG14 (CA info) or DG15 (AA key).
The hashes are real SHA-256 digests of the served files, so Document.Verify passes.
The signer is a throwaway self-signed certificate: Passive Authentication fails against
the empty CSCA pool the drivers use, which gmrtd records without aborting the read.

The harness chip is consistent: it serves DG1 (a TD3 MRZ for the ICAO 9303 Part 11 worked
example document used by every harness profile) and DG2 (ICAO 9303 Part 10: a biometric
information template holding one ISO/IEC 19794-5 face record with a small greyscale JPEG), and
EF.COM and EF.SOD list exactly the data groups it serves (DG1 and DG2, plus DG14 or DG15 when a
profile configures them). Doc 9303 makes DG1 and DG2 mandatory.

Outputs (committed): simulator/fixtures/dg1.hex, dg2.hex, sod-dg1-dg2.hex, sod-dg1-dg2-dg14.hex,
sod-dg1-dg2-dg15.hex, and (with --vsmartcard) vsc-*.hex for the independent vsmartcard chip.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import io
from pathlib import Path

from asn1crypto import algos, cms, core, x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "simulator" / "fixtures"
DG_FILES = {
    14: ROOT / "testdata" / "dg14" / "ca-v2-sample.hex",
    15: ROOT / "testdata" / "dg15" / "aa-rsa-sample.hex",
}


ID_MRTD_LDS_SECURITY_OBJECT = "2.23.136.1.1.1"
DIGEST_OID = {"sha256": "sha256"}
HASH_CLS = {"sha256": hashes.SHA256}
CMS_SIG = {"sha256": "sha256_rsa"}


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = []
    while n:
        b.insert(0, n & 0xFF)
        n >>= 8
    return bytes([0x80 | len(b)]) + bytes(b)


def retag_as_ef_sod(content_info_der: bytes) -> bytes:
    return b"\x77" + _der_len(len(content_info_der)) + content_info_der


def sign_sod(key: rsa.RSAPrivateKey, certs_der: list[bytes], econtent: bytes, digest: str) -> bytes:
    h = hashes.Hash(HASH_CLS[digest]())
    h.update(econtent)
    message_digest = h.finalize()
    signed_attrs = cms.CMSAttributes(
        [
            cms.CMSAttribute(
                {"type": "content_type", "values": [cms.ContentType(ID_MRTD_LDS_SECURITY_OBJECT)]}
            ),
            cms.CMSAttribute({"type": "message_digest", "values": [core.OctetString(message_digest)]}),
        ]
    )
    signature = key.sign(signed_attrs.dump(), padding.PKCS1v15(), HASH_CLS[digest]())
    dsc_der = certs_der[0]
    signer_info = cms.SignerInfo(
        {
            "version": "v1",
            "sid": cms.SignerIdentifier(
                {
                    "issuer_and_serial_number": cms.IssuerAndSerialNumber(
                        {
                            "issuer": asn1_x509.Certificate.load(dsc_der)["tbs_certificate"]["issuer"],
                            "serial_number": asn1_x509.Certificate.load(dsc_der)["tbs_certificate"][
                                "serial_number"
                            ],
                        }
                    )
                }
            ),
            "digest_algorithm": algos.DigestAlgorithm({"algorithm": DIGEST_OID[digest]}),
            "signed_attrs": signed_attrs,
            "signature_algorithm": algos.SignedDigestAlgorithm({"algorithm": CMS_SIG[digest]}),
            "signature": signature,
        }
    )
    cert_set = [
        cms.CertificateChoices({"certificate": asn1_x509.Certificate.load(d)}) for d in certs_der
    ]
    signed_data = cms.SignedData(
        {
            "version": "v3",
            "digest_algorithms": cms.DigestAlgorithms(
                [algos.DigestAlgorithm({"algorithm": DIGEST_OID[digest]})]
            ),
            "encap_content_info": cms.EncapsulatedContentInfo(
                {
                    "content_type": cms.ContentType(ID_MRTD_LDS_SECURITY_OBJECT),
                    "content": core.ParsableOctetString(econtent),
                }
            ),
            "certificates": cms.CertificateSet(cert_set),
            "signer_infos": cms.SignerInfos([signer_info]),
        }
    )
    return cms.ContentInfo({"content_type": "signed_data", "content": signed_data}).dump()


def lds_security_object(dg_hashes: dict[int, bytes]) -> bytes:
    hash_alg = algos.DigestAlgorithm({"algorithm": "sha256"}).dump()
    entries = b""
    for number, digest in sorted(dg_hashes.items()):
        body = core.Integer(number).dump() + core.OctetString(digest).dump()
        entries += b"\x30" + _der_len(len(body)) + body
    values = b"\x30" + _der_len(len(entries)) + entries
    body = core.Integer(0).dump() + hash_alg + values
    return b"\x30" + _der_len(len(body)) + body


def self_signed() -> tuple[rsa.RSAPrivateKey, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "XX"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic Document Signer"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc))
        .not_valid_after(datetime.datetime(2035, 1, 1, tzinfo=datetime.timezone.utc))
        .sign(key, hashes.SHA256())
    )
    return key, cert.public_bytes(serialization.Encoding.DER)


# MRZ of the independent vsmartcard chip (tools/vsmartcard/emrtd_card.py); TD1, 90 characters.
VSC_MRZ = (
    b"IDD<<T220001293<<<<<<<<<<<<<<<"
    b"6408125<2010315D<<<<<<<<<<<<<4"
    b"MUSTERMANN<<ERIKA<<<<<<<<<<<<<"
)


def tlv(tag: bytes, value: bytes) -> bytes:
    n = len(value)
    if n < 0x80:
        length = bytes([n])
    elif n < 0x100:
        length = bytes([0x81, n])
    else:
        length = bytes([0x82]) + n.to_bytes(2, "big")
    return tag + length + value


def write_hex(name: str, data: bytes) -> None:
    out = OUT / name
    out.write_bytes(data.hex().upper().encode("ascii") + bytes([0x0A]))
    print(f"wrote {out.relative_to(ROOT)} ({len(data)} bytes)")


def check_digit(s: str) -> str:
    total = 0
    for i, c in enumerate(s):
        v = 0 if c == "<" else int(c) if c.isdigit() else ord(c) - 55
        total += v * (7, 3, 1)[i % 3]
    return str(total % 10)


def harness_td3_mrz() -> bytes:
    """TD3 MRZ for document L898902C, born 690806, expiring 940623 (the MRZ data of every
    harness profile; ICAO 9303 Part 11 worked example), with valid check digits."""
    line1 = "P<UTOERIKSSON<<ANNA<MARIA".ljust(44, "<")
    doc, dob, doe, opt = "L898902C<", "690806", "940623", "ZE184226B".ljust(14, "<")
    parts = [doc + check_digit(doc), dob + check_digit(dob), doe + check_digit(doe), opt + check_digit(opt)]
    line2 = parts[0] + "UTO" + parts[1] + "F" + parts[2] + parts[3]
    line2 += check_digit(parts[0] + parts[1] + parts[2] + parts[3])
    assert len(line1) == 44 and len(line2) == 44, (len(line1), len(line2))
    return (line1 + line2).encode("ascii")


def face_jpeg() -> tuple[bytes, int, int]:
    """A 48 x 64 greyscale JPEG (oval on a flat background), deterministic."""
    from PIL import Image, ImageDraw
    w, h = 48, 64
    img = Image.new("L", (w, h), 200)
    ImageDraw.Draw(img).ellipse((10, 8, 38, 52), fill=120)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=False, progressive=False)
    return buf.getvalue(), w, h


def dg2_face() -> bytes:
    """DG2 per ICAO 9303 Part 10 (tag 75, one 7F61 group with one 7F60 template) carrying an
    ISO/IEC 19794-5:2005 facial record (FAC, version 010) with one JPEG image."""
    jpeg, w, h = face_jpeg()
    face_info = bytes(4 + 2 + 1 + 1 + 1 + 3 + 2 + 3 + 3)       # length set below; no feature points
    # face type 1 (full frontal), JPEG, width, height, colour space 3 (8-bit greyscale), source, device, quality
    image_info = bytes([0x01, 0x00]) + w.to_bytes(2, "big") + h.to_bytes(2, "big") + bytes([0x03, 0x00]) + bytes(4)
    face_len = len(face_info) + len(image_info) + len(jpeg)
    face_info = face_len.to_bytes(4, "big") + face_info[4:]
    record = b"FAC\x00" + b"010\x00" + (14 + face_len).to_bytes(4, "big") + (1).to_bytes(2, "big")
    record += face_info + image_info + jpeg
    bht = tlv(bytes([0xA1]), tlv(bytes([0x80]), bytes([0x01, 0x01])) + tlv(bytes([0x81]), bytes([0x02]))
              + tlv(bytes([0x87]), bytes([0x01, 0x01])) + tlv(bytes([0x88]), bytes([0x00, 0x08])))
    bit = tlv(bytes([0x7F, 0x60]), bht + tlv(bytes([0x5F, 0x2E]), record))
    return tlv(bytes([0x75]), tlv(bytes([0x7F, 0x61]), tlv(bytes([0x02]), bytes([0x01])) + bit))


def harness_fixtures(key: rsa.RSAPrivateKey, cert: bytes) -> None:
    """DG1, DG2, and SODs listing DG1 and DG2 alone or with DG14 / DG15, with real hashes."""
    dg1 = tlv(bytes([0x61]), tlv(bytes([0x5F, 0x1F]), harness_td3_mrz()))
    dg2 = dg2_face()
    write_hex("dg1.hex", dg1)
    write_hex("dg2.hex", dg2)
    dgs = {n: bytes.fromhex(p.read_text(encoding="utf-8").strip()) for n, p in DG_FILES.items()}
    for name, groups in (("sod-dg1-dg2.hex", {1: dg1, 2: dg2}),
                         ("sod-dg1-dg2-dg14.hex", {1: dg1, 2: dg2, 14: dgs[14]}),
                         ("sod-dg1-dg2-dg15.hex", {1: dg1, 2: dg2, 15: dgs[15]})):
        econtent = lds_security_object({n: hashlib.sha256(b).digest() for n, b in groups.items()})
        write_hex(name, retag_as_ef_sod(sign_sod(key, [cert], econtent, "sha256")))


def vsmartcard_fixtures(key: rsa.RSAPrivateKey, cert: bytes) -> None:
    """DG1 with the vsmartcard MRZ, and SODs listing DG1 (and DG15) with real hashes."""
    dg1 = tlv(bytes([0x61]), tlv(bytes([0x5F, 0x1F]), VSC_MRZ))
    dg15 = bytes.fromhex(DG_FILES[15].read_text(encoding="utf-8").strip())
    write_hex("vsc-dg1.hex", dg1)
    for name, groups in (("vsc-sod-dg1.hex", {1: dg1}), ("vsc-sod-dg1-dg15.hex", {1: dg1, 15: dg15})):
        econtent = lds_security_object({n: hashlib.sha256(b).digest() for n, b in groups.items()})
        write_hex(name, retag_as_ef_sod(sign_sod(key, [cert], econtent, "sha256")))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsmartcard", action="store_true", help="also rewrite the vsmartcard chip's fixtures")
    args = ap.parse_args()
    key, cert = self_signed()
    harness_fixtures(key, cert)
    if args.vsmartcard:
        vsmartcard_fixtures(key, cert)


if __name__ == "__main__":
    main()
