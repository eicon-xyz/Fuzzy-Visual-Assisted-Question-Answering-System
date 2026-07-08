"""Verify SSH tunnel to GPU OmniParser API on local :9800."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("OMNIPARSER_URL", "http://127.0.0.1:9800").rstrip("/")
TIMEOUT = float(os.environ.get("OMNIPARSER_HEALTH_TIMEOUT", "5"))


def check(base_url: str = DEFAULT_URL) -> tuple[bool, dict | str]:
    url = f"{base_url}/health"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return False, f"HTTP {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ready"):
                return False, "ready=false (模型仍在加载?)"
            return True, data
    except urllib.error.URLError as exc:
        return False, str(exc.reason if hasattr(exc, "reason") else exc)
    except TimeoutError:
        return False, f"timeout ({TIMEOUT}s)"


def main() -> int:
    ok, detail = check()
    print(f"[check] {DEFAULT_URL}/health -> {'OK' if ok else 'FAIL'}")
    if ok:
        print(json.dumps(detail, ensure_ascii=False, indent=2))
        return 0
    print(f"[check] {detail}", file=sys.stderr)
    print(
        "\n请先:\n"
        "  一键: 根目录 启动HAJIMI.bat\n"
        "  或:\n"
        "  1. 终端1: scripts\\start_tunnel_9800.bat  (paramiko 免输密码)\n"
        "  2. 远程: python scripts\\gpu_group2_remote.py start-9800\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
