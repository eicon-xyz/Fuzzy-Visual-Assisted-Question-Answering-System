"""将 B 端用户设置合并写入 server/.env（本地部署模式）。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict

from core.defaults import (
    DEFAULT_DEMO_KEY,
    DEFAULT_OMNI_GPU_API_URL,
    DEFAULT_OMNI_LOCAL_URL,
)

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "server" / ".env"
EXAMPLE_PATH = ROOT / "server" / ".env.example"


def _parse_env_lines(text: str) -> list[str]:
    return text.splitlines()


def _upsert_env_lines(lines: list[str], updates: Dict[str, str]) -> list[str]:
    seen = set()
    pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
    new_lines: list[str] = []
    for line in lines:
        m = pattern.match(line.strip())
        if m and m.group(1) in updates:
            key = m.group(1)
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)
    for key, val in updates.items():
        if key not in seen:
            if new_lines and new_lines[-1].strip():
                new_lines.append("")
            new_lines.append(f"{key}={val}")
    return new_lines


def _default_omni_url(data: dict) -> str:
    mode = data.get("deployment_mode", "gpu_api")
    omni = data.get("omniparser") or {}
    if omni.get("url"):
        return str(omni["url"]).strip()
    if mode == "gpu_api":
        return DEFAULT_OMNI_GPU_API_URL
    return DEFAULT_OMNI_LOCAL_URL


def _omni_timeout(data: dict) -> str:
    mode = data.get("deployment_mode", "gpu_api")
    return "120" if mode in ("gpu_api", "intranet") else "360"


def _settings_to_env_updates(data: dict) -> Dict[str, str]:
    llm = data.get("llm") or {}
    omni_url = _default_omni_url(data)
    omni_timeout = _omni_timeout(data)
    updates: Dict[str, str] = {
        "OMNIPARSER_URL": omni_url,
        "OMNIPARSER_LOCAL_URL": omni_url,
        "OMNIPARSER_TIMEOUT": omni_timeout,
        "OMNIPARSER_LOCAL_TIMEOUT": omni_timeout,
        "HAJIMI_DEMO_KEY": (data.get("demo_key") or DEFAULT_DEMO_KEY).strip(),
    }
    speed = (data.get("llm_speed_mode") or "fast").strip().lower()
    routing = (data.get("routing_mode") or speed or "fast").strip().lower()
    if speed in ("fast", "balanced", "precision"):
        updates["LLM_SPEED_MODE"] = speed
    if routing in ("auto", "fast", "balanced", "precision", "l5"):
        updates["ROUTING_MODE"] = routing
    elif speed in ("fast", "balanced", "precision"):
        updates["ROUTING_MODE"] = speed
    mode = data.get("deployment_mode", "gpu_api")
    if mode == "gpu_api":
        updates["OMNIPARSER_RETRY"] = "0"
    if llm.get("api_key"):
        updates["LLM_API_KEY"] = llm["api_key"].strip()
        if llm.get("base_url"):
            updates["LLM_BASE_URL"] = llm["base_url"].strip()
        if llm.get("model"):
            updates["LLM_MODEL"] = llm["model"].strip()
    a_url = (data.get("a_end_url") or "").strip()
    if a_url:
        from urllib.parse import urlparse

        parsed = urlparse(a_url)
        if parsed.port:
            updates["HAJIMI_PORT"] = str(parsed.port)
        if parsed.hostname:
            updates["HAJIMI_HOST"] = parsed.hostname

    l4 = data.get("l4") or {}
    if isinstance(l4, dict):
        updates["L4_PLANNER_MODEL"] = str(l4.get("planner_model") or "").strip()
        updates["L4_LOCATOR_MODEL"] = str(l4.get("locator_model") or "").strip()
        updates["L4_PLANNER_USE_VISION"] = (
            "true" if l4.get("planner_use_vision") else "false"
        )
        updates["L4_STRICT_LOCATE"] = "true" if l4.get("strict_locate", True) else "false"
        updates["L4_PIPELINE_ENABLED"] = (
            "true" if l4.get("pipeline_enabled", True) else "false"
        )
    return updates


def sync_server_env(data: dict) -> Path:
    """合并写入 server/.env，保留未在 updates 中的既有键。"""
    updates = _settings_to_env_updates(data)
    if ENV_PATH.is_file():
        text = ENV_PATH.read_text(encoding="utf-8")
    elif EXAMPLE_PATH.is_file():
        text = EXAMPLE_PATH.read_text(encoding="utf-8")
    else:
        text = ""
    lines = _parse_env_lines(text)
    merged = _upsert_env_lines(lines, updates)
    content = "\n".join(merged).rstrip() + "\n"
    tmp = ENV_PATH.with_suffix(".env.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, ENV_PATH)
    return ENV_PATH
