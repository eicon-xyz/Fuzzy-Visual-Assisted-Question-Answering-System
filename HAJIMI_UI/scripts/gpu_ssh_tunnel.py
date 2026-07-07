"""SSH local port forward via paramiko — no interactive password prompt."""
from __future__ import annotations

import argparse
import os
import select
import socket
import socketserver
import sys
import threading
import time

try:
    import paramiko
except ImportError:
    print("Install paramiko: pip install paramiko", file=sys.stderr)
    raise SystemExit(1) from None

HOST = os.environ.get("HAJIMI_GPU_HOST", "10.246.2.7")
SSH_PORT = int(os.environ.get("HAJIMI_GPU_SSH_PORT", "12202"))
USER = os.environ.get("HAJIMI_GPU_USER", "student")
PASSWORD = os.environ.get("HAJIMI_GPU_SSH_PASSWORD", "group2-ssh-123")
SSH_KEY = os.environ.get("HAJIMI_GPU_SSH_KEY", "").strip()
CONNECT_TIMEOUT = int(os.environ.get("HAJIMI_GPU_SSH_TIMEOUT", "30"))

_transport: paramiko.Transport | None = None
_remote_host = "127.0.0.1"
_remote_port = 9800


class _ForwardHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        assert _transport is not None
        try:
            chan = _transport.open_channel(
                "direct-tcpip",
                (_remote_host, _remote_port),
                self.request.getpeername(),
            )
        except Exception as exc:
            print(f"[tunnel] channel failed: {exc}", file=sys.stderr)
            return
        if chan is None:
            return
        try:
            while True:
                r, _, _ = select.select([self.request, chan], [], [], 1.0)
                if self.request in r:
                    data = self.request.recv(65536)
                    if not data:
                        break
                    chan.send(data)
                if chan in r:
                    data = chan.recv(65536)
                    if not data:
                        break
                    self.request.send(data)
        finally:
            chan.close()
            self.request.close()


def _connect() -> paramiko.SSHClient:
    print(f"[tunnel] SSH {USER}@{HOST}:{SSH_PORT} ...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict = {
        "hostname": HOST,
        "port": SSH_PORT,
        "username": USER,
        "timeout": CONNECT_TIMEOUT,
    }
    if SSH_KEY:
        kwargs["key_filename"] = SSH_KEY
        print(f"[tunnel] auth: key {SSH_KEY}")
    else:
        kwargs["password"] = PASSWORD
        print("[tunnel] auth: password (HAJIMI_GPU_SSH_PASSWORD or group default)")
    client.connect(**kwargs)
    print("[tunnel] connected")
    return client


def run_tunnel(
    local_port: int,
    remote_host: str = "127.0.0.1",
    remote_port: int = 9800,
    bind_host: str = "127.0.0.1",
) -> None:
    global _transport, _remote_host, _remote_port
    _remote_host = remote_host
    _remote_port = remote_port

    client = _connect()
    _transport = client.get_transport()
    if _transport is None:
        raise RuntimeError("SSH transport unavailable")

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Server((bind_host, local_port), _ForwardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    print(
        f"[tunnel] {bind_host}:{local_port} -> {remote_host}:{remote_port} "
        f"(via {HOST}) — keep this window open"
    )
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n[tunnel] closing ...")
    finally:
        server.shutdown()
        client.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Paramiko SSH -L local forward (no password prompt)")
    p.add_argument("--local-port", type=int, default=int(os.environ.get("HAJIMI_TUNNEL_LOCAL", "9800")))
    p.add_argument("--remote-host", default=os.environ.get("HAJIMI_TUNNEL_REMOTE_HOST", "127.0.0.1"))
    p.add_argument("--remote-port", type=int, default=int(os.environ.get("HAJIMI_TUNNEL_REMOTE_PORT", "9800")))
    p.add_argument("--bind", default="127.0.0.1", help="Local bind address")
    args = p.parse_args()
    run_tunnel(args.local_port, args.remote_host, args.remote_port, args.bind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
