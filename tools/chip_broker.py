#!/usr/bin/env python3
"""Chip broker for readers that cannot start processes themselves (the iOS test runs inside
the simulator). The reader connects to --port and sends one length-prefixed JSON header:

    {"run_id": "...", "profile": "profiles/pace/....json"}

The broker starts the chip the profile asks for (cmd/chip-serve, or the independent vsmartcard
chip for "peer": "vsmartcard"), lets it connect back, and relays vpcd messages in both
directions until either side closes. It then writes <out>/<run_id>.chip.json with the chip's
delivered-fault report, which the host-side collector merges into the run artifact.
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_msg(sock: socket.socket) -> bytes | None:
    hdr = recv_exact(sock, 2)
    if hdr is None:
        return None
    (n,) = struct.unpack("!H", hdr)
    return recv_exact(sock, n) if n else b""


def recv_exact(sock: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def serve_one(reader: socket.socket, chip_serve: str, out: Path) -> None:
    header = json.loads((read_msg(reader) or b"{}").decode("utf-8"))
    run_id, profile_path = header["run_id"], header["profile"]
    profile = json.loads((ROOT / profile_path).read_text(encoding="utf-8"))
    report = out / f"{run_id}.chip.json"

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    if profile.get("peer") == "vsmartcard":
        vs = profile.get("vsmartcard", {})
        cmd = [sys.executable, str(ROOT / "tools/vsmartcard/emrtd_card.py"), "--port", str(port),
               "--card-access", vs.get("card_access", "pace-only")]
        if vs.get("dg15"):
            cmd.append("--dg15")
        if vs.get("aa_sw"):
            cmd += ["--aa-sw", vs["aa_sw"]]
    else:
        cmd = [chip_serve, "-profile", str(ROOT / profile_path), "-port", str(port), "-report", str(report)]
    chip_proc = subprocess.Popen(cmd, cwd=ROOT)
    listener.settimeout(30)
    chip, _ = listener.accept()
    listener.close()

    sent_aa = threading.Event()

    def reader_to_chip() -> None:
        # Watch for INTERNAL AUTHENTICATE so vsmartcard runs can report whether AA was sent.
        try:
            while True:
                msg = read_msg(reader)
                if msg is None:
                    break
                if len(msg) >= 2 and msg[1] == 0x88:
                    sent_aa.set()
                chip.sendall(struct.pack("!H", len(msg)) + msg)
        except OSError:
            pass
        finally:
            for s in (reader, chip):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    t1 = threading.Thread(target=reader_to_chip)
    t2 = threading.Thread(target=pump, args=(chip, reader))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    try:
        chip_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        chip_proc.kill()
    if profile.get("peer") == "vsmartcard":
        aa = bool(profile.get("vsmartcard", {}).get("aa_sw")) and sent_aa.is_set()
        report.write_text(json.dumps({"fault_delivered": {"AA": aa}}), encoding="utf-8")
    reader.close()
    chip.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=35963)
    ap.add_argument("--chip-serve", default=str(ROOT / "bin/chip-serve"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", args.port))
    srv.listen(1)
    print(f"chip broker listening on 127.0.0.1:{args.port}", flush=True)
    while True:
        reader, _ = srv.accept()
        serve_one(reader, args.chip_serve, args.out)


if __name__ == "__main__":
    main()
