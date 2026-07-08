"""Emit cmd.exe set lines for B-end proxy from user_settings.json.

Used by apply_proxy_env.bat. Default: proxy disabled (prints rem only).
"""
from __future__ import annotations

import json
import os
import sys


def _settings_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "HAJIMI", "user_settings.json")


def main() -> int:
    enabled = False
    http_p = "http://127.0.0.1:7890"
    https_p = http_p
    path = _settings_path()
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            enabled = bool(data.get("proxy_enabled", False))
            http_p = (data.get("http_proxy") or http_p).strip() or http_p
            https_p = (data.get("https_proxy") or "").strip() or http_p
        except Exception:
            enabled = False

    if not enabled:
        print("rem HAJIMI proxy disabled")
        return 0

    no_proxy = "127.0.0.1,localhost,::1"
    # Escape caret for cmd when printing - URLs rare here
    print(f"set HTTP_PROXY={http_p}")
    print(f"set HTTPS_PROXY={https_p}")
    print(f"set http_proxy={http_p}")
    print(f"set https_proxy={https_p}")
    print(f"set NO_PROXY={no_proxy}")
    print(f"set no_proxy={no_proxy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
