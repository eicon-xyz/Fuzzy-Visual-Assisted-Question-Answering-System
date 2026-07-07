"""Write user_settings + server/.env for local GPU API mode (SSH tunnel :9800)."""
from __future__ import annotations

import os
import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.defaults import DEFAULT_A_URL, DEFAULT_DEMO_KEY, DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODEL
from core.env_sync import ENV_PATH, EXAMPLE_PATH, _parse_env_lines, _upsert_env_lines, sync_server_env
from core.user_settings import DEFAULT_SETTINGS, apply_user_settings, load_user_settings, save_user_settings, _settings_path

GPU_API_OMNI_URL = "http://127.0.0.1:9800"
OMNI_TIMEOUT = "120"


def _ensure_env_file() -> None:
    if not ENV_PATH.is_file() and EXAMPLE_PATH.is_file():
        ENV_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def _upsert_env_keys(extra: dict[str, str]) -> None:
    text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.is_file() else ""
    merged = _upsert_env_lines(_parse_env_lines(text), extra)
    ENV_PATH.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")


def _read_env_llm() -> dict[str, str]:
    if not ENV_PATH.is_file():
        return {}
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _merge_llm_settings(data: dict) -> None:
    existing = load_user_settings() or {}
    llm = (existing.get("llm") or {}) if isinstance(existing, dict) else {}
    if llm.get("api_key") or llm.get("base_url"):
        data["llm"] = {
            "base_url": llm.get("base_url") or DEFAULT_LLM_BASE_URL,
            "api_key": llm.get("api_key") or "",
            "model": llm.get("model") or DEFAULT_LLM_MODEL,
        }
        return
    env = _read_env_llm()
    if env.get("LLM_API_KEY"):
        data["llm"] = {
            "base_url": env.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
            "api_key": env.get("LLM_API_KEY", ""),
            "model": env.get("LLM_MODEL", DEFAULT_LLM_MODEL),
        }


def build_settings() -> dict:
    data = deepcopy(DEFAULT_SETTINGS)
    data["deployment_mode"] = "gpu_api"
    data["a_end_url"] = DEFAULT_A_URL
    data["demo_key"] = DEFAULT_DEMO_KEY
    data["omniparser"] = {"url": GPU_API_OMNI_URL, "gpu_url": ""}
    _merge_llm_settings(data)
    return data


def main() -> int:
    _ensure_env_file()
    settings = build_settings()
    save_user_settings(settings)
    sync_server_env(settings)
    _upsert_env_keys(
        {
            "OMNIPARSER_URL": GPU_API_OMNI_URL,
            "OMNIPARSER_LOCAL_URL": GPU_API_OMNI_URL,
            "OMNIPARSER_TIMEOUT": OMNI_TIMEOUT,
            "OMNIPARSER_LOCAL_TIMEOUT": OMNI_TIMEOUT,
        }
    )
    apply_user_settings(settings)
    print("[setup] GPU API mode (local A-end + tunnel :9800)")
    print(f"[setup] user_settings: {_settings_path()}")
    print(f"[setup] server/.env:   {ENV_PATH}")
    print(f"[setup] OMNIPARSER_URL={GPU_API_OMNI_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
