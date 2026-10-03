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
session. --aa-sw makes INTERNAL AUTHENTICATE fail with that status word; vsmartcard frames
the error with its own secure-messaging code.
"""

from __future__ import annotations

import argparse
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
    ap.add_argument("--dg15", action="store_true", help="serve DG15 so readers attempt Active Authentication")
    ap.add_argument("--aa-sw", default="", help="fail INTERNAL AUTHENTICATE with this status word (hex)")
    ap.add_argument("--log-level", default="WARNING", help="vsmartcard logging level")
    ap.add_argument("--card-access", choices=("pace-only", "npa"), default="pace-only",
                    help="EF.CardAccess: the PACEInfo only, or the nPA card's own (TA, CA and PACE infos)")
    args = ap.parse_args()

    vicc = VirtualICC(None, "nPA", args.host, args.port, logginglevel=getattr(logging, args.log_level.upper()))
    os_ = vicc.os
    shipped = os_.SAM.mrz
    assert shipped[:59] == MRZ[:59] and shipped[60:] == MRZ[60:], "vsmartcard nPA MRZ changed; update the harness profile"
    os_.SAM.mrz = MRZ
    os_.mf.append(emrtd_application(os_.mf, args.dg15))
    if args.card_access == "pace-only":
        os_.mf.select("fid", 0x011C).data = CARD_ACCESS_PACE_ONLY

    if args.aa_sw:
        sw = int(args.aa_sw, 16)

        def failing_internal_authenticate(p1, p2, data):
            raise InjectedSwError(sw)

        os_.ins2handler[0x88] = failing_internal_authenticate

    try:
        vicc.run()
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
