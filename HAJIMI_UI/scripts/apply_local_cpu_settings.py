"""Write user_settings for offline CPU local stack (dev fallback)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.defaults import DEFAULT_A_PORT, DEFAULT_DEMO_KEY
from core.user_settings import _settings_path, apply_user_settings, save_settings_fragment


def main() -> int:
    base = f"http://127.0.0.1:{DEFAULT_A_PORT}"
    merged = save_settings_fragment(
        {
            "deployment_mode": "local",
            "a_end_url": base,
            "demo_key": DEFAULT_DEMO_KEY,
            "routing_mode": "l5",
        }
    )
    apply_user_settings(merged)
    print(f"[local-cpu] settings -> {_settings_path()}")
    print("            deployment_mode=local  (CPU OmniParser :8002)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
