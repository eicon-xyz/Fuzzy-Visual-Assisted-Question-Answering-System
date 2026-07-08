"""Warn if campus GPU tunnel is available while starting local demo."""
from __future__ import annotations

import sys

from core.deployment_resolver import _find_campus_gpu_url


def main() -> int:
    url = _find_campus_gpu_url()
    if url:
        print(f"[WARN] Campus GPU available at {url}")
        print("       Consider: python scripts/b_group2_intranet_setup.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
