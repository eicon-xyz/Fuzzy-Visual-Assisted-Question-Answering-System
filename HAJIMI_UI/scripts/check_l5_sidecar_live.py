"""Exit 0 if L5 Sidecar process is listening (health/live or health, incl. 503)."""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request


def is_live(port: int) -> bool:
    base = f"http://127.0.0.1:{port}"
    for path in ("/api/demo/health/live", "/api/demo/health"):
        try:
            with urllib.request.urlopen(base + path, timeout=3) as resp:
                if resp.status in (200, 503):
                    return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            if exc.code == 503:
                return True
        except Exception:
            continue
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe L5 Sidecar readiness")
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    return 0 if is_live(args.port) else 1


if __name__ == "__main__":
    raise SystemExit(main())
