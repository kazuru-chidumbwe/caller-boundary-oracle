#!/usr/bin/env python3
"""Independent chip for positive controls and cross-checks, built on vsmartcard.

The card is vsmartcard's nPA emulation, whose PACE and secure messaging are implemented by
OpenPACE (neither shares code with the harness simulators or with the libraries under test),
plus an ICAO eMRTD application (EF.COM, DG1, EF.SOD and optionally DG15). PACE uses the
nPA card's own MRZ data with a valid TD1 composite check digit (the shipped MRZ has '<'
there, which readers reject when parsing DG1):

    IDD<<T220001293<<<<<<<<<<<<<<<
    6408125<2010315D<<<<<<<<<<<<<4
    MUSTERMANN<<ERIKA<<<<<<<<<<<<<

i.e. document number T22000129, date of birth 640812, date of expiry 201031. The PACE key
derives from those three fields and their own check digits, which the change leaves intact.

The nPA card implements PACE but not Basic Access Control, which eMRTDs that support PACE also
offer. A reader that falls back to BAC after a PACE failure would otherwise be refused (6985)
for a reason no passport gives. The card therefore also answers BAC: EXTERNAL AUTHENTICATE
outside an EAC session runs vsmartcard's own ICAO BAC (cards/ePass.py, keys from the same MRZ)
and hands secure messaging to that session. Its responses follow Doc 9303 Part 11: DO'87'
(when there is data), DO'99' (the status word) and DO'8E' (MAC) on every protected response,
errors included; vsmartcard's generic ISO 7816 secure messaging leaves out DO'99' and the MAC
on errors.

Requires the pinned vsmartcard checkout with tools/vsmartcard/vsmartcard-python3.patch
applied (scripts/bootstrap-vsmartcard.sh), and the OpenPACE Python bindings.

The card connects to a driver acting as the reader (vpcd socket protocol) and serves one
session. What it serves and which step it fails come from the profile's "vsmartcard" object
(--profile): dg15, card_access, aa_sw (INTERNAL AUTHENTICATE answers with that status word,
framed by vsmartcard's own secure-messaging code), relay (a port: pass everything to
tools/vsmartcard/phone_hub.py, which holds a phone reading a real chip; see relay()), and pace_sw with pace_step ("mse" for the
first MSE:Set AT, "ga1" to "ga4" for the PACE General Authenticate steps, answered in plaintext
since secure messaging is not yet established). ga4_body instead lets the card run the real
PACE step 4 (it verifies the reader's token and switches to the PACE session keys as usual)
and answers 9000 with a changed response body: "empty-7c" (7C00, no authentication token),
"truncated-86" (7C04 86 08 and the first two token bytes: outer length consistent, token
cut short), "wrong-token" (full-length token with every bit inverted) or "no-data" (no
response data). --report writes {"fault_delivered": {...}} as
soon as an injected failure is sent, the same report cmd/chip-serve writes, so every driver
observes delivery the same way.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import virtualsmartcard.CryptoUtils as vsCrypto
from virtualsmartcard.SmartcardFilesystem import DF, TransparentStructureEF
from virtualsmartcard.SmartcardSAM import SAM
from virtualsmartcard.cards.ePass import PassportSAM, ePass_SE
from virtualsmartcard.SWutils import SwError
from virtualsmartcard.TLVutils import pack
from virtualsmartcard.VirtualSmartcard import VirtualICC

FIXTURES = Path(__file__).resolve().parents[2] / "simulator" / "fixtures"
EMRTD_AID = bytes.fromhex("A0000002471001")
# EF.CardAccess with only the PACEInfo the nPA card implements (id-PACE-ECDH-GM-AES-CBC-CMAC-128,
# version 2, brainpoolP256r1), as most passports carry. The card's PACE takes its parameters
# from EF.CardSecurity, so this changes only what readers see in EF.CardAccess.
CARD_ACCESS_PACE_ONLY = bytes.fromhex("31143012060A04007F0007020204020202010202010D")
MRZ = (
    b"IDD<<T220001293<<<<<<<<<<<<<<<"
    b"6408125<2010315D<<<<<<<<<<<<<4"
    b"MUSTERMANN<<ERIKA<<<<<<<<<<<<<"
)


def _ga4_token(resp: bytes) -> bytes:
    """The authentication token T_PICC from the card's own step-4 response (7C L 86 08 T ...)."""
    if len(resp) < 12 or resp[0] != 0x7C or resp[2] != 0x86 or resp[3] != 0x08:
        raise RuntimeError(f"unexpected PACE step-4 response {resp.hex()}")
    return resp[4:12]


# Response bodies for a PACE step 4 that the card itself completed (keys already switched).
GA4_BODIES = {
    "empty-7c": lambda resp: bytes.fromhex("7C00"),
    "truncated-86": lambda resp: bytes.fromhex("7C048608") + _ga4_token(resp)[:2],
    "wrong-token": lambda resp: bytes.fromhex("7C0A8608") + bytes(b ^ 0xFF for b in _ga4_token(resp)),
    "no-data": lambda resp: b"",
}


class InjectedSwError(SwError):
    """SwError for any status word: vsmartcard's SwError only accepts words in its message
    table (6FFF is not), and a KeyError there would drop the connection instead of answering."""

    def __init__(self, sw: int):
        Exception.__init__(self, f"injected status word {sw:04X}")
        self.sw = sw
        self.message = f"injected status word {sw:04X}"


class Report:
    """Writes which injected failures were delivered to the reader."""

    def __init__(self, path: str):
        self.path = Path(path) if path else None
        self.delivered = {"PACE": False, "BAC": False, "AA": False}
        self.write()

    def mark(self, mechanism: str) -> None:
        self.delivered[mechanism] = True
        self.write()

    def write(self) -> None:
        if self.path is not None:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"fault_delivered": self.delivered}), encoding="utf-8")
            tmp.replace(self.path)


class IcaoBacSE(ePass_SE):
    """BAC secure messaging with ICAO Doc 9303 Part 11 response protection."""

    def compute_cryptographic_checksum(self, p1, p2, data):
        # vsmartcard prepends the SSC as a minimal-length integer, so a counter whose top byte
        # is zero (about 1 session in 256) is MACed as 7 bytes; Doc 9303 uses all 8.
        if p1 != 0x8E or p2 != 0x80:
            raise InjectedSwError(0x6A86)
        self.ssc += 1
        return vsCrypto.crypto_checksum("CC", self.cct.key, self.ssc.to_bytes(8, "big") + data)

    def protect_response(self, sw, result):
        out = b""
        if result:
            cryptogram = b"" + self.encipher(0x82, 0x80, result)
            out += pack([(0x87, len(cryptogram), cryptogram)])
        out += pack([(0x99, 2, sw.to_bytes(2, "big"))])
        mac = self.compute_cryptographic_checksum(0x8E, 0x80, vsCrypto.append_padding(self.cct.blocklength, out))
        out += pack([(0x8E, len(mac), mac)])
        return sw, out


def install_bac(os_, mrz: bytes) -> None:
    """Answer BAC with vsmartcard's ePass implementation, keyed from the TD1 MRZ."""
    line1, line2 = mrz[:30], mrz[30:60]
    # document number + check digit, date of birth + check digit, date of expiry + check digit
    seed = hashlib.sha1(line1[5:15] + line2[0:7] + line2[8:15]).digest()[:16]
    bac = PassportSAM.__new__(PassportSAM)  # its constructor expects a TD3 DG1 at a fixed path
    SAM.__init__(bac, None, None, os_.mf, default_se=IcaoBacSE)
    bac.KSeed = seed
    bac.KEnc = PassportSAM.derive_key(seed, 1)
    bac.KMac = PassportSAM.derive_key(seed, 2)
    npa_sam = os_.SAM
    npa_external_authenticate = os_.ins2handler[0x82]

    def external_authenticate(p1, p2, data):
        if getattr(npa_sam.current_SE, "eac_step", 0) == 4:
            return npa_external_authenticate(p1, p2, data)  # Terminal Authentication
        bac.last_challenge = npa_sam.last_challenge
        sw, resp = bac.external_authenticate(p1, p2, data)
        os_.SAM = bac  # secure messaging now uses the BAC session keys
        return sw, resp

    os_.ins2handler[0x82] = external_authenticate


def _recv(sock) -> bytes | None:
    head = b""
    while len(head) < 2:
        part = sock.recv(2 - len(head))
        if not part:
            return None
        head += part
    n = int.from_bytes(head, "big")
    body = b""
    while len(body) < n:
        part = sock.recv(n - len(body))
        if not part:
            return None
        body += part
    return body


def _send(sock, msg: bytes) -> None:
    sock.sendall(len(msg).to_bytes(2, "big") + msg)


# A refusal by the real chip counts as the delivered fault for its mechanism, so the oracle classifies a
# genuine failure the same way as an injected one. Instruction bytes: 86 PACE General Authenticate,
# 82 EXTERNAL AUTHENTICATE (BAC), 88 INTERNAL AUTHENTICATE (Active Authentication).
RELAY_FAULT_INS = {0x86: "PACE", 0x82: "BAC", 0x88: "AA"}


def relay(host: str, port: int, hub_port: int, report: "Report") -> None:
    """Relay mode (real chip): act as the card toward the driver and pass every message to the phone
    hub (tools/vsmartcard/phone_hub.py), which holds the connection to the phone reading the real
    chip. Nothing is logged or stored except the delivered-fault report."""
    import socket
    drv = socket.create_connection((host, port), timeout=120)
    hub = socket.create_connection(("127.0.0.1", hub_port), timeout=120)
    try:
        while True:
            msg = _recv(drv)
            if msg is None:
                break
            _send(hub, msg)
            if len(msg) == 1 and msg[0] != 0x04:
                continue  # power control: no answer in the vpcd protocol
            rsp = _recv(hub)
            if rsp is None:
                break
            if len(msg) >= 4 and len(rsp) >= 2:
                mech = RELAY_FAULT_INS.get(msg[1])
                sw = rsp[-2:]
                if mech and sw != b"\x90\x00" and sw[0] != 0x61:
                    report.mark(mech)
            _send(drv, rsp)
    finally:
        hub.close()
        drv.close()


def hexfile(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="utf-8").strip())


def emrtd_application(mf, with_dg15: bool) -> DF:
    df = DF(parent=mf, fid=0x0004, dfname=EMRTD_AID, bertlv_data=[])
    tags = b"\x61\x6f" if with_dg15 else b"\x61"
    com = pack([(0x5F01, 4, b"0107"), (0x5F36, 6, b"040000"), (0x5C, len(tags), tags)])
    # Short EF identifiers as in Doc 9303 Part 10 (EF.COM 1E, EF.SOD 1D, DGn = n), so readers
    # that use READ BINARY with an SFI find the files.
    def ef(fid: int, sfi: int, data: bytes) -> TransparentStructureEF:
        return TransparentStructureEF(parent=df, fid=fid, shortfid=sfi, filedescriptor=0, data=data)

    df.append(ef(0x011E, 0x1E, pack([(0x60, len(com), com)])))
    df.append(ef(0x0101, 0x01, hexfile("vsc-dg1.hex")))
    sod = "vsc-sod-dg1-dg15.hex" if with_dg15 else "vsc-sod-dg1.hex"
    df.append(ef(0x011D, 0x1D, hexfile(sod)))
    if with_dg15:
        dg15 = bytes.fromhex((FIXTURES.parents[1] / "testdata" / "dg15" / "aa-rsa-sample.hex").read_text().strip())
        df.append(ef(0x010F, 0x0F, dg15))
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--profile", default="", help="profile JSON; its \"vsmartcard\" object configures the card")
    ap.add_argument("--report", default="", help="write the delivered-fault report here")
    ap.add_argument("--log-level", default="WARNING", help="vsmartcard logging level")
    args = ap.parse_args()
    vs = json.loads(Path(args.profile).read_text(encoding="utf-8")).get("vsmartcard", {}) if args.profile else {}
    if vs.get("relay"):
        relay(args.host, args.port, int(vs["relay"]), Report(args.report))
        return
    card_access = vs.get("card_access", "pace-only")
    if card_access not in ("pace-only", "npa"):
        raise SystemExit(f"unknown card_access {card_access!r}")
    pace_step = vs.get("pace_step", "")
    if pace_step not in ("", "mse", "ga1", "ga2", "ga3", "ga4"):
        raise SystemExit(f"unknown pace_step {pace_step!r}")
    ga4_body = vs.get("ga4_body", "")
    if ga4_body not in ("",) + tuple(GA4_BODIES):
        raise SystemExit(f"unknown ga4_body {ga4_body!r}")
    if ga4_body and pace_step:
        raise SystemExit("ga4_body and pace_step are exclusive")
    report = Report(args.report)

    vicc = VirtualICC(None, "nPA", args.host, args.port, logginglevel=getattr(logging, args.log_level.upper()))
    os_ = vicc.os
    shipped = os_.SAM.mrz
    assert shipped[:59] == MRZ[:59] and shipped[60:] == MRZ[60:], "vsmartcard nPA MRZ changed; update the harness profile"
    os_.SAM.mrz = MRZ
    install_bac(os_, MRZ)
    os_.mf.append(emrtd_application(os_.mf, bool(vs.get("dg15"))))
    if card_access == "pace-only":
        os_.mf.select("fid", 0x011C).data = CARD_ACCESS_PACE_ONLY

    if vs.get("aa_sw"):
        aa_sw = int(vs["aa_sw"], 16)

        def failing_internal_authenticate(p1, p2, data):
            report.mark("AA")
            raise InjectedSwError(aa_sw)

        os_.ins2handler[0x88] = failing_internal_authenticate

    if pace_step:
        pace_sw = int(vs["pace_sw"], 16)
        if pace_step == "mse":
            real_mse = os_.ins2handler[0x22]
            mse_calls = [0]

            def failing_mse(p1, p2, data):
                # Only the first MSE:Set AT (the one that starts PACE) fails.
                mse_calls[0] += 1
                if mse_calls[0] == 1:
                    report.mark("PACE")
                    raise InjectedSwError(pace_sw)
                return real_mse(p1, p2, data)

            os_.ins2handler[0x22] = failing_mse
        else:
            target = int(pace_step[2])
            real_ga = os_.ins2handler[0x86]
            ga_calls = [0]

            def failing_ga(p1, p2, data):
                # PACE is the first four General Authenticate commands of the session.
                ga_calls[0] += 1
                if ga_calls[0] == target:
                    report.mark("PACE")
                    raise InjectedSwError(pace_sw)
                return real_ga(p1, p2, data)

            os_.ins2handler[0x86] = failing_ga

    if vs.get("observe_refusals"):
        # Record the card's own refusals (not injected) as delivered faults, as relay mode does for
        # a real chip, so a wrong-key cell is classified the same way on both paths. Off by default.
        for ins, mech in RELAY_FAULT_INS.items():
            inner = os_.ins2handler[ins]

            def observed(p1, p2, data, inner=inner, mech=mech):
                try:
                    sw, resp = inner(p1, p2, data)
                except SwError:
                    report.mark(mech)
                    raise
                if sw != 0x9000 and (sw >> 8) != 0x61:
                    report.mark(mech)
                return sw, resp

            os_.ins2handler[ins] = observed

    if ga4_body:
        real_ga = os_.ins2handler[0x86]
        ga_calls = [0]

        def changed_ga4(p1, p2, data):
            ga_calls[0] += 1
            sw, resp = real_ga(p1, p2, data)
            if ga_calls[0] != 4:
                return sw, resp
            report.mark("PACE")
            return sw, GA4_BODIES[ga4_body](resp)

        os_.ins2handler[0x86] = changed_ga4

    try:
        vicc.run()
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
