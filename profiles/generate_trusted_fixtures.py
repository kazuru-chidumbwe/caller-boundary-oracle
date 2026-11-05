#!/usr/bin/env python3
"""Build the trusted-chain chip: a document gmrtd can verify end to end.

The harness chip (generate_chip_fixtures.py) signs EF.SOD with a throwaway self-signed signer and
holds no Chip Authentication or Active Authentication private key, so Passive Authentication
fails against any CSCA pool and CA or AA can never succeed. That is right for the failure cells,
but it cannot measure a library option that accepts a document only when it is verifiably
authentic (gmrtd RequireAuthenticDocument, v1.4.0 on): such an option would refuse every
document for the PA failure alone.

This script writes a second, separate fixture set under simulator/fixtures/trusted/. The
existing fixtures are not touched, so every earlier cell stays byte for byte the same.

  csca.hex      synthetic CSCA certificate (C=NL), loaded into the reader's CSCA pool
  dg1.hex       TD3 MRZ, same document number and dates as every harness profile (so the BAC
                keys do not change), issuing state NLD instead of the fictitious UTO, which
                gmrtd cannot resolve to a country and so cannot match to a CSCA
  dg2.hex       same face record as the harness chip
  dg14.hex      ChipAuthenticationInfo (id-CA-ECDH-3DES-CBC-CBC, v1) and
                ChipAuthenticationPublicKeyInfo (id-PK-ECDH, P-256) for a key the chip holds
  dg15.hex      RSA 1024 Active Authentication public key the chip holds
  ca-key.hex    the chip's CA private scalar (synthetic test key)
  aa-key.hex    the chip's AA private key, PKCS#1 DER (synthetic test key)
  sod-*.hex     EF.SOD over DG1, DG2 (and DG14, DG15 or both), signed by a Document Signer issued by
                the CSCA

All keys are synthetic, generated here, and used only by the simulator.
Usage: python profiles/generate_trusted_fixtures.py
"""

from __future__ import annotations

import datetime
import hashlib
from pathlib import Path

from asn1crypto import core, keys as asn1_keys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

import generate_chip_fixtures as base

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "simulator" / "fixtures" / "trusted"

OID_CA_ECDH_3DES = "0.4.0.127.0.7.2.2.3.2.1"  # id-CA-ECDH-3DES-CBC-CBC
OID_PK_ECDH = "0.4.0.127.0.7.2.2.1.2"        # id-PK-ECDH

NOT_BEFORE = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
NOT_AFTER = datetime.datetime(2040, 1, 1, tzinfo=datetime.timezone.utc)


def write(name: str, data: bytes) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_bytes(data.hex().upper().encode("ascii") + b"\n")
    print(f"wrote {(OUT / name).relative_to(ROOT)} ({len(data)} bytes)")


def name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "NL"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Synthetic Test Issuer"),
                      x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def csca_and_ds() -> tuple[bytes, rsa.RSAPrivateKey, bytes]:
    csca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csca = (x509.CertificateBuilder()
            .subject_name(name("Synthetic Test CSCA")).issuer_name(name("Synthetic Test CSCA"))
            .public_key(csca_key.public_key()).serial_number(1)
            .not_valid_before(NOT_BEFORE).not_valid_after(NOT_AFTER)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(csca_key.public_key()), critical=False)
            .sign(csca_key, hashes.SHA256()))
    ds_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ds = (x509.CertificateBuilder()
          .subject_name(name("Synthetic Test Document Signer")).issuer_name(csca.subject)
          .public_key(ds_key.public_key()).serial_number(2)
          .not_valid_before(NOT_BEFORE).not_valid_after(NOT_AFTER)
          .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(csca_key.public_key()), critical=False)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ds_key.public_key()), critical=False)
          .sign(csca_key, hashes.SHA256()))
    return (csca.public_bytes(serialization.Encoding.DER), ds_key,
            ds.public_bytes(serialization.Encoding.DER))


def trusted_td3_mrz() -> bytes:
    """The harness MRZ (L898902C, 690806, 940623) with issuing state and nationality NLD."""
    mrz = base.harness_td3_mrz().decode("ascii")
    line1, line2 = mrz[:44], mrz[44:]
    line1 = line1[:2] + "NLD" + line1[5:]
    line2 = line2[:10] + "NLD" + line2[13:]
    return (line1 + line2).encode("ascii")


def dg14(ca_key: ec.EllipticCurvePrivateKey) -> bytes:
    spki = ca_key.public_key().public_bytes(serialization.Encoding.DER,
                                            serialization.PublicFormat.SubjectPublicKeyInfo)
    spki = asn1_keys.PublicKeyInfo.load(spki)
    ca_body = core.ObjectIdentifier(OID_CA_ECDH_3DES).dump() + core.Integer(1).dump()
    ca_info = b"\x30" + base._der_len(len(ca_body)) + ca_body
    pk_body = core.ObjectIdentifier(OID_PK_ECDH).dump() + spki.dump()
    pk_info = b"\x30" + base._der_len(len(pk_body)) + pk_body
    infos = ca_info + pk_info
    sec_infos = b"\x31" + base._der_len(len(infos)) + infos
    return b"\x6E" + base._der_len(len(sec_infos)) + sec_infos


def dg15(aa_key: rsa.RSAPrivateKey) -> bytes:
    spki = aa_key.public_key().public_bytes(serialization.Encoding.DER,
                                            serialization.PublicFormat.SubjectPublicKeyInfo)
    return b"\x6F" + base._der_len(len(spki)) + spki


def main() -> None:
    csca, ds_key, ds = csca_and_ds()
    ca_key = ec.generate_private_key(ec.SECP256R1())
    aa_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)

    dg1 = base.tlv(bytes([0x61]), base.tlv(bytes([0x5F, 0x1F]), trusted_td3_mrz()))
    dg2 = base.dg2_face()
    d14, d15 = dg14(ca_key), dg15(aa_key)

    write("csca.hex", csca)
    write("dg1.hex", dg1)
    write("dg2.hex", dg2)
    write("dg14.hex", d14)
    write("dg15.hex", d15)
    write("ca-key.hex", ca_key.private_numbers().private_value.to_bytes(32, "big"))
    write("aa-key.hex", aa_key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.TraditionalOpenSSL,
                                             serialization.NoEncryption()))
    for fname, groups in (("sod-dg1-dg2.hex", {1: dg1, 2: dg2}),
                          ("sod-dg1-dg2-dg14.hex", {1: dg1, 2: dg2, 14: d14}),
                          ("sod-dg1-dg2-dg15.hex", {1: dg1, 2: dg2, 15: d15}),
                          ("sod-dg1-dg2-dg14-dg15.hex", {1: dg1, 2: dg2, 14: d14, 15: d15})):
        econtent = base.lds_security_object({n: hashlib.sha256(b).digest() for n, b in groups.items()})
        write(fname, base.retag_as_ef_sod(base.sign_sod(ds_key, [ds], econtent, "sha256")))


if __name__ == "__main__":
    main()
