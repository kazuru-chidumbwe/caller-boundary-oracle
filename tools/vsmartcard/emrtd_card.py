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
framed by vsmartcard's own secure-messaging code), dg14 (serve DG14, the harness chip's CA sample, listed in
EF.COM and EF.SOD), ca_sw (MSE:Set AT or Set KAT for Chip Authentication answers with that status word under
secure messaging), relay (a port: pass everything to
tools/vsmartcard/phone_hub.py, which holds a phone reading a real chip; see relay()), and pace_sw with pace_step ("mse" for the
first MSE:Set AT, "ga1" to "ga4" for the PACE General Authenticate steps, answered in plaintext
since secure messaging is not yet established); pace_channel ("no_response", "timeout" or
"transport_abort") at that step answers with an empty frame instead (after 50 ms for "timeout"),
the channel faults of the harness chip. ga4_body instead lets the card run the real
PACE step 4 (it verifies the reader's token and switches to the PACE session keys as usual)
and answers 9000 with a changed response body: "empty-7c" (7C00, no authentication token),
"truncated-86" (7C04 86 08 and the first two token bytes: outer length consistent, token
cut short), "wrong-token" (full-length token with every bit inverted) or "no-data" (no
response data). access_control "enforce" makes the eMRTD application refuse plain access as a
genuine chip does: a SELECT of an LDS file (EF.COM, EF.SOD, DG1 to DG16) by file identifier, and
any READ BINARY or READ RECORD of an LDS file (by short EF identifier, by file identifier, or of
the currently selected file), answer 6982 (security status not satisfied) unless the command
carries secure messaging. Files in the MF (EF.CardAccess, EF.DIR) stay readable in plain, as Doc
9303 Part 10 allows. Without it (the default) the card serves LDS files in plain whatever the
access-control state, as vsmartcard does, which is how a clone or an emulator behaves after a
failed BAC. --report writes {"fault_delivered": {...}} as
soon as an injected failure is sent, the same report cmd/chip-serve writes, so every driver
observes delivery the same way.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
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


# Channel faults as the harness chip delivers them (no_response, timeout, transport_abort: an empty frame).
CHANNEL_FAULTS = ("no_response", "timeout", "transport_abort")


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


# LDS1 files of the eMRTD application (Doc 9303 Part 10): EF.COM 011E (SFI 1E), EF.SOD 011D (SFI 1D),
# DG1 to DG16 0101 to 0110 (SFI 01 to 10).
LDS_FIDS = {0x011E, 0x011D} | {0x0100 + n for n in range(1, 17)}
LDS_SFIS = {0x1E, 0x1D} | set(range(1, 17))
SW_SECURITY_STATUS = b"\x69\x82"


def _lc_data(msg: bytes) -> bytes:
    """Command data of a short or extended APDU (header CLA INS P1 P2, then Lc and data)."""
    if len(msg) <= 5:
        return b""
    if msg[4] == 0 and len(msg) >= 7:  # extended length: 00 Lc1 Lc2
        n = int.from_bytes(msg[5:7], "big")
        return msg[7:7 + n]
    return msg[5:5 + msg[4]]


def install_access_control(os_, emrtd_df) -> None:
    """Refuse plain (unprotected) access to LDS files with 6982, as a genuine chip does before, and
    after a failed, access control. Commands with secure messaging (CLA bits 3 and 4) pass to the
    card unchanged, so a reader that completed BAC or PACE reads as before."""
    inner_execute = os_.execute

    def lds_selected() -> bool:
        ef = os_.mf.currentEF()
        return ef is not None and ef.parent is emrtd_df and ef.fid in LDS_FIDS

    def enforcing_execute(msg: bytes) -> bytes:
        if len(msg) >= 4 and (msg[0] & 0x0C) == 0:
            ins, p1, p2 = msg[1], msg[2], msg[3]
            deny = False
            if ins == 0xA4 and p1 in (0x00, 0x02):
                data = _lc_data(msg)
                deny = len(data) == 2 and int.from_bytes(data, "big") in LDS_FIDS
            elif ins == 0xB0:
                deny = (p1 & 0x1F) in LDS_SFIS if p1 & 0x80 else lds_selected()
            elif ins == 0xB1:
                fid = (p1 << 8) | p2
                deny = fid in LDS_FIDS if fid else lds_selected()
            elif ins in (0xB2, 0xB3):
                sfi = p2 >> 3
                deny = sfi in LDS_SFIS if sfi else lds_selected()
            if deny:
                return SW_SECURITY_STATUS
        return inner_execute(msg)

    os_.execute = enforcing_execute


def hexfile(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="utf-8").strip())


def emrtd_application(mf, with_dg15: bool, with_dg14: bool = False) -> DF:
    if with_dg14 and with_dg15:
        raise SystemExit("dg14 and dg15 together have no SOD fixture")
    df = DF(parent=mf, fid=0x0004, dfname=EMRTD_AID, bertlv_data=[])
    tags = b"\x61\x6f" if with_dg15 else b"\x61\x6e" if with_dg14 else b"\x61"
    com = pack([(0x5F01, 4, b"0107"), (0x5F36, 6, b"040000"), (0x5C, len(tags), tags)])
    # Short EF identifiers as in Doc 9303 Part 10 (EF.COM 1E, EF.SOD 1D, DGn = n), so readers
    # that use READ BINARY with an SFI find the files.
    def ef(fid: int, sfi: int, data: bytes) -> TransparentStructureEF:
        return TransparentStructureEF(parent=df, fid=fid, shortfid=sfi, filedescriptor=0, data=data)

    df.append(ef(0x011E, 0x1E, pack([(0x60, len(com), com)])))
    df.append(ef(0x0101, 0x01, hexfile("vsc-dg1.hex")))
    sod = "vsc-sod-dg1-dg15.hex" if with_dg15 else "vsc-sod-dg1-dg14.hex" if with_dg14 else "vsc-sod-dg1.hex"
    df.append(ef(0x011D, 0x1D, hexfile(sod)))
    if with_dg14:
        # A5-9: the Chip Authentication info and key the harness chip serves (testdata/dg14/ca-v2-sample.hex)
        dg14 = bytes.fromhex((FIXTURES.parents[1] / "testdata" / "dg14" / "ca-v2-sample.hex").read_text().strip())
        df.append(ef(0x010E, 0x0E, dg14))
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
    if card_access not in ("pace-only", "npa", "none"):
        raise SystemExit(f"unknown card_access {card_access!r}")
    pace_step = vs.get("pace_step", "")
    if pace_step not in ("", "mse", "ga1", "ga2", "ga3", "ga4"):
        raise SystemExit(f"unknown pace_step {pace_step!r}")
    ga4_body = vs.get("ga4_body", "")
    if ga4_body not in ("",) + tuple(GA4_BODIES):
        raise SystemExit(f"unknown ga4_body {ga4_body!r}")
    if ga4_body and pace_step:
        raise SystemExit("ga4_body and pace_step are exclusive")
    pace_channel = vs.get("pace_channel", "")
    if pace_channel not in ("",) + CHANNEL_FAULTS:
        raise SystemExit(f"unknown pace_channel {pace_channel!r}")
    if pace_channel and not pace_step:
        raise SystemExit("pace_channel needs pace_step")
    access_control = vs.get("access_control", "")
    if access_control not in ("", "enforce"):
        raise SystemExit(f"unknown access_control {access_control!r}")
    report = Report(args.report)

    vicc = VirtualICC(None, "nPA", args.host, args.port, logginglevel=getattr(logging, args.log_level.upper()))
    os_ = vicc.os
    shipped = os_.SAM.mrz
    assert shipped[:59] == MRZ[:59] and shipped[60:] == MRZ[60:], "vsmartcard nPA MRZ changed; update the harness profile"
    os_.SAM.mrz = MRZ
    install_bac(os_, MRZ)
    emrtd_df = emrtd_application(os_.mf, bool(vs.get("dg15")), bool(vs.get("dg14")))
    os_.mf.append(emrtd_df)
    if access_control == "enforce":
        install_access_control(os_, emrtd_df)
    if card_access == "pace-only":
        os_.mf.select("fid", 0x011C).data = CARD_ACCESS_PACE_ONLY
    elif card_access == "none":
        # A chip without PACE: no EF.CardAccess, so readers use BAC (Doc 9303 Part 11 §4.2).
        os_.mf.remove(os_.mf.select("fid", 0x011C))

    if vs.get("aa_sw"):
        aa_sw = int(vs["aa_sw"], 16)

        def failing_internal_authenticate(p1, p2, data):
            report.mark("AA")
            raise InjectedSwError(aa_sw)

        os_.ins2handler[0x88] = failing_internal_authenticate

    if vs.get("ca_sw"):
        # A5-9: Chip Authentication rejected at its first command, as the harness chip's CA profiles do
        # (ca_fail_on mse_set_at): MSE:Set AT for CA (P1P2 41A4, AES) or MSE:Set KAT (41A6, 3DES) answers with
        # the status word, framed by vsmartcard's secure messaging (the PACE channel). Other MSE commands
        # (PACE C1A4, TA 81A4) pass to the card unchanged.
        ca_sw = int(vs["ca_sw"], 16)
        report.delivered["CA"] = False
        report.write()
        real_mse_ca = os_.ins2handler[0x22]

        def failing_ca_mse(p1, p2, data):
            if p1 == 0x41 and p2 in (0xA4, 0xA6):
                report.mark("CA")
                raise InjectedSwError(ca_sw)
            return real_mse_ca(p1, p2, data)

        os_.ins2handler[0x22] = failing_ca_mse

    if pace_channel:
        # A5-9b: the channel faults of the harness chip (simulator/pace_bac_transceiver.go deliverPaceFailure), at
        # the same PACE step pace_sw would fail: the card answers that command with an empty frame, after 50 ms
        # for "timeout". The card's own PACE code never sees the command.
        target_ins = 0x22 if pace_step == "mse" else 0x86
        target_n = 1 if pace_step == "mse" else int(pace_step[2])
        seen = [0]
        inner_execute = os_.execute

        def channel_fault_execute(msg: bytes) -> bytes:
            if len(msg) >= 4 and msg[1] == target_ins:
                seen[0] += 1
                if seen[0] == target_n:
                    report.mark("PACE")
                    if pace_channel == "timeout":
                        time.sleep(0.05)
                    return b""
            return inner_execute(msg)

        os_.execute = channel_fault_execute
    elif pace_step:
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
        # A string value names the report key every refusal is recorded under (e.g. "PACE" for the
        # access-control step of a chip without PACE, whose refusal comes at BAC).
        as_key = vs["observe_refusals"] if isinstance(vs["observe_refusals"], str) else None
        for ins, mech in RELAY_FAULT_INS.items():
            mech = as_key or mech
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
