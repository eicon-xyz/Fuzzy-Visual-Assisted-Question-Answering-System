"""Local probe for GPU remote access experiments (Phase 0 / 实验1).

Usage (from repo root):
  python scripts/gpu_connectivity_probe.py
  python scripts/gpu_connectivity_probe.py --host 10.246.2.7 --ssh-port 12202
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request

DEFAULT_HOST = "10.246.2.7"
DEFAULT_SSH_PORT = 12202


def tcp_ok(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_get(url: str, timeout: float = 5.0) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode(errors="replace")[:500]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")[:500]
    except Exception as exc:
        return None, str(exc)


def main() -> int:
    p = argparse.ArgumentParser(description="Probe campus GPU direct access (8010/9800/SSH)")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--ssh-port", type=int, default=DEFAULT_SSH_PORT)
    args = p.parse_args()
    host = args.host

    print(f"=== GPU connectivity probe: {host} ===\n")

    ssh_ok = tcp_ok(host, args.ssh_port)
    print(f"[1/4] SSH TCP :{args.ssh_port} -> {'OK' if ssh_ok else 'FAIL'}")

    for label, port, path in (
        ("A-end", 8010, "/api/demo/health"),
        ("OmniParser API", 9800, "/health"),
    ):
        url = f"http://{host}:{port}{path}"
        code, body = http_get(url)
        status = "OK" if code == 200 else "FAIL"
        print(f"[{label}] GET {url} -> HTTP {code} ({status})")
        if code == 200:
            try:
                data = json.loads(body)
                print(f"  {json.dumps(data, ensure_ascii=False)[:200]}")
            except json.JSONDecodeError:
                print(f"  {body[:120]}")

    print("\n=== Summary ===")
    if not ssh_ok:
        print("SSH unreachable — connect campus VPN and open group2 host on GPU platform.")
        print("Then: python scripts/gpu_group2_remote.py phase0")
        return 2
    print("SSH reachable — run: python scripts/gpu_group2_remote.py services")
    return 0


if __name__ == "__main__":
    sys.exit(main())
