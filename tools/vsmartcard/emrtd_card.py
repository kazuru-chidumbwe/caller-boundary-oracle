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

Requires the pinned vsmartcard checkout with tools/vsmartcard/vsmartcard-python3.patch
applied (scripts/bootstrap-vsmartcard.sh), and the OpenPACE Python bindings.

The card connects to a driver acting as the reader (vpcd socket protocol) and serves one
session. What it serves and which step it fails come from the profile's "vsmartcard" object
(--profile): dg15, card_access, aa_sw (INTERNAL AUTHENTICATE answers with that status word,
framed by vsmartcard's own secure-messaging code), and pace_sw with pace_step ("mse" for the
first MSE:Set AT, "ga1" to "ga4" for the PACE General Authenticate steps, answered in plaintext
since secure messaging is not yet established). --report writes {"fault_delivered": {...}} as
soon as an injected failure is sent, the same report cmd/chip-serve writes, so every driver
observes delivery the same way.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from virtualsmartcard.SmartcardFilesystem import DF, TransparentStructureEF
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
        self.delivered = {"PACE": False, "AA": False}
        self.write()

    def mark(self, mechanism: str) -> None:
        self.delivered[mechanism] = True
        self.write()

    def write(self) -> None:
        if self.path is not None:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"fault_delivered": self.delivered}), encoding="utf-8")
            tmp.replace(self.path)


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
    card_access = vs.get("card_access", "pace-only")
    if card_access not in ("pace-only", "npa"):
        raise SystemExit(f"unknown card_access {card_access!r}")
    pace_step = vs.get("pace_step", "")
    if pace_step not in ("", "mse", "ga1", "ga2", "ga3", "ga4"):
        raise SystemExit(f"unknown pace_step {pace_step!r}")
    report = Report(args.report)

    vicc = VirtualICC(None, "nPA", args.host, args.port, logginglevel=getattr(logging, args.log_level.upper()))
    os_ = vicc.os
    shipped = os_.SAM.mrz
    assert shipped[:59] == MRZ[:59] and shipped[60:] == MRZ[60:], "vsmartcard nPA MRZ changed; update the harness profile"
    os_.SAM.mrz = MRZ
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

    try:
        vicc.run()
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
