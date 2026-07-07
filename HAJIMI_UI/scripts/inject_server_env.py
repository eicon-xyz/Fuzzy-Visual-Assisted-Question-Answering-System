"""Print CMD set lines for key server/.env vars (used by start_server.bat)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values  # noqa: E402

ENV_PATH = ROOT / "server" / ".env"
KEYS = (
    "OMNIPARSER_URL",
    "OMNIPARSER_LOCAL_URL",
    "OMNIPARSER_TIMEOUT",
    "OMNIPARSER_LOCAL_TIMEOUT",
    "OMNIPARSER_LOCAL_MAX_SIDE",
    "HAJIMI_HOST",
    "HAJIMI_PORT",
    "HAJIMI_DEMO_KEY",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
)


def main() -> int:
    if not ENV_PATH.is_file():
        return 0
    print('set "NO_PROXY=127.0.0.1,localhost"')
    print('set "no_proxy=127.0.0.1,localhost"')
    values = dotenv_values(ENV_PATH)
    for key in KEYS:
        val = values.get(key)
        if val is None or str(val).strip() == "":
            continue
        text = str(val).replace('"', '""')
        print(f'set "{key}={text}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
