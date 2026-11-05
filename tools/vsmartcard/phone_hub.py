#!/usr/bin/env python3
"""Phone hub for the real-chip runs: one phone in, one harness run at a time out.

The phone runs vsmartcard's Remote Smart Card Reader app, which connects to a vpcd server and
relays each command over NFC to the document on the phone. This hub is that vpcd server
(--phone-host/--phone-port, 35963 is the app's default). A harness run reaches it through
emrtd_card.py in relay mode (profile {"vsmartcard": {"relay": RELAY_PORT}}), which connects to
--relay-port on 127.0.0.1. The hub forwards each message from the run to the phone and the answer
back, so every driver talks to the real chip through its usual vpcd transport.

The phone connection is kept across runs; if it drops, the hub waits for the phone again and the
run in progress ends (its driver records a transport failure). A software card can stand in for
the phone (emrtd_card.py --host 127.0.0.1 --port PHONE_PORT) to test the whole path.

Nothing from the document is logged: the status file holds only connection state, counts and the slowest
chip reply of the last run (milliseconds).
"""
from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path


def recv(sock) -> bytes | None:
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


def send(sock, msg: bytes) -> None:
    sock.sendall(len(msg).to_bytes(2, "big") + msg)


class Status:
    def __init__(self, path: str):
        self.path = Path(path) if path else None
        self.s = {"phone_connected": False, "phone_connects": 0, "runs": 0, "apdus": 0, "since": time.time()}
        self.write()

    def set(self, **kw) -> None:
        self.s.update(kw)
        self.write()

    def write(self) -> None:
        if self.path:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.s), encoding="utf-8")
            tmp.replace(self.path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--phone-host", default="0.0.0.0", help="address the phone connects to (e.g. the Tailscale IP)")
    ap.add_argument("--phone-port", type=int, default=35963)
    ap.add_argument("--relay-port", type=int, default=35964)
    ap.add_argument("--reply-timeout", type=float, default=60.0, help="seconds to wait for the phone's answer")
    ap.add_argument("--status", default="", help="write connection state and counts here")
    a = ap.parse_args()
    st = Status(a.status)

    phone_srv = socket.create_server((a.phone_host, a.phone_port))
    relay_srv = socket.create_server(("127.0.0.1", a.relay_port))
    phone = None
    while True:
        if phone is None:
            st.set(phone_connected=False)
            phone, _ = phone_srv.accept()
            phone.settimeout(a.reply_timeout)
            st.set(phone_connected=True, phone_connects=st.s["phone_connects"] + 1)
        run, _ = relay_srv.accept()
        st.set(runs=st.s["runs"] + 1, last_run_max_reply_ms=0)
        try:
            while True:
                msg = recv(run)
                if msg is None:
                    break
                send(phone, msg)
                if len(msg) == 1 and msg[0] != 0x04:
                    continue
                t0 = time.monotonic()
                rsp = recv(phone)
                # Slowest chip reply in this run: a chip that delays after failed access attempts shows here.
                ms = int((time.monotonic() - t0) * 1000)
                if ms > st.s["last_run_max_reply_ms"]:
                    st.s["last_run_max_reply_ms"] = ms
                if rsp is None:
                    raise ConnectionError("phone closed")
                if len(msg) > 1:
                    st.s["apdus"] += 1
                send(run, rsp)
            st.write()
        except (OSError, ConnectionError):
            try:
                phone.close()
            except OSError:
                pass
            phone = None
        finally:
            st.write()
            run.close()


if __name__ == "__main__":
    main()
