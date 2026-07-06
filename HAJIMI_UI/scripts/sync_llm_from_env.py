"""Sync user_settings llm block from server/.env LLM_* keys (keeps DeepSeek in .env only)."""
from __future__ import annotations

import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.defaults import DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODEL
from core.env_sync import ENV_PATH
from core.user_settings import (
    DEFAULT_SETTINGS,
    _settings_path,
    apply_user_settings,
    load_user_settings,
    save_user_settings,
)


def _read_env() -> dict[str, str]:
    if not ENV_PATH.is_file():
        return {}
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def main() -> int:
    env = _read_env()
    api_key = env.get("LLM_API_KEY", "").strip()
    base_url = env.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).strip()
    model = env.get("LLM_MODEL", DEFAULT_LLM_MODEL).strip()

    if not api_key:
        print("[sync_llm] LLM_API_KEY not set in server/.env — skip")
        return 1

    data = load_user_settings() or deepcopy(DEFAULT_SETTINGS)
    data["llm"] = {"base_url": base_url, "api_key": api_key, "model": model}
    save_user_settings(data)
    apply_user_settings(data)
    print("[sync_llm] user_settings llm synced from server/.env")
    print(f"[sync_llm] model={model} base_url={base_url}")
    print(f"[sync_llm] path={_settings_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
