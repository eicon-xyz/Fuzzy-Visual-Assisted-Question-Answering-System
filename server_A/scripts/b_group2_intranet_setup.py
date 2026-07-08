"""B 端：SSH 本地转发 + health + 写入内网 API 设置（纯 paramiko，无 sshtunnel）。"""
from __future__ import annotations

import json
import os
import select
import socket
import socketserver
import sys
import threading
import time
import urllib.request
from pathlib import Path

import paramiko

HOST = os.environ.get("HAJIMI_GPU_HOST", "10.246.2.7")
SSH_PORT = int(os.environ.get("HAJIMI_GPU_SSH_PORT", "12202"))
USER = os.environ.get("HAJIMI_GPU_USER", "student")
PASSWORD = os.environ.get("HAJIMI_GPU_SSH_PASSWORD", "group2-ssh-123")
LOCAL_PORT = int(os.environ.get("HAJIMI_TUNNEL_LOCAL", "0"))


def _pick_local_port() -> int:
    if LOCAL_PORT:
        return LOCAL_PORT
    for port in (8010, 18010, 28010):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("no free local port for tunnel (tried 8010, 18010, 28010)")

_transport: paramiko.Transport | None = None


class _ForwardHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        assert _transport is not None
        try:
            chan = _transport.open_channel(
                "direct-tcpip",
                (REMOTE_HOST, REMOTE_PORT),
                self.request.getpeername(),
            )
        except Exception as exc:
            print(f"[tunnel] channel failed: {exc}", file=sys.stderr)
            return
        if chan is None:
            return
        try:
            while True:
                r, _, _ = select.select([self.request, chan], [], [])
                if self.request in r:
                    data = self.request.recv(1024)
                    if not data:
                        break
                    chan.send(data)
                if chan in r:
                    data = chan.recv(1024)
                    if not data:
                        break
                    self.request.send(data)
        finally:
            chan.close()
            self.request.close()


def _start_forward_server(local_port: int) -> socketserver.ThreadingTCPServer:
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    return Server(("127.0.0.1", local_port), _ForwardHandler)


REMOTE_HOST = "127.0.0.1"
REMOTE_PORT = 8010
DEMO_KEY = "hajimi-demo-2026"


def fetch_health(base: str) -> dict:
    req = urllib.request.Request(f"{base}/api/demo/health")
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())


def save_settings(base: str) -> Path:
    folder = Path(os.environ.get("LOCALAPPDATA", "")) / "HAJIMI"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "user_settings.json"
    data = {
        "deployment_mode": "intranet",
        "a_end_url": base,
        "demo_key": DEMO_KEY,
        "llm": {
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "model": "deepseek-chat",
        },
        "omniparser": {"url": "http://127.0.0.1:8002", "gpu_url": ""},
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    global _transport
    local_port = _pick_local_port()
    base = f"http://127.0.0.1:{local_port}"
    demo_key = DEMO_KEY

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=SSH_PORT, username=USER, password=PASSWORD, timeout=20)
    _transport = client.get_transport()
    assert _transport is not None

    server = _start_forward_server(local_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)
    print(f"[tunnel] localhost:{local_port} -> {REMOTE_HOST}:{REMOTE_PORT} via {HOST}")

    def fetch() -> dict:
        req = urllib.request.Request(f"{base}/api/demo/health")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())

    try:
        health = fetch()
        print("[health]", json.dumps(health, ensure_ascii=False))
        if health.get("status") != "ok":
            raise SystemExit("health status not ok")
        folder = Path(os.environ.get("LOCALAPPDATA", "")) / "HAJIMI"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "user_settings.json"
        data = {
            "deployment_mode": "intranet",
            "a_end_url": base,
            "demo_key": demo_key,
            "llm": {
                "base_url": "https://api.deepseek.com",
                "api_key": "",
                "model": "deepseek-chat",
            },
            "omniparser": {"url": "http://127.0.0.1:8002", "gpu_url": ""},
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[settings] wrote {path}")
        print("[OK] 网络方案 B (SSH 隧道) | Base URL:", base)
        if health.get("omniparser_ready") is False:
            print("[WARN] omniparser_ready=false")
        return base, health
    finally:
        server.shutdown()
        client.close()


if __name__ == "__main__":
    main()
