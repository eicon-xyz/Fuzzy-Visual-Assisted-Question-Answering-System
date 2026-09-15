"""将 B 端用户设置合并写入 L5 Sidecar (server_A/server/.env)。

L4/旧 A 端 (HAJIMI_UI/server) 已删除：本模块只服务 :8011 Sidecar。
注意：OMNIPARSER_* / ROUTING_MODE 不在同步键内 —— 由启动脚本
apply_l5_settings.py 直接写 Sidecar .env，防止 user_settings 回滚部署配置。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict

from core.defaults import (
    DEFAULT_DEMO_KEY,
    DEFAULT_L5_HOST,
    DEFAULT_L5_PORT,
)

_L5_SIDECAR_SYNC_KEYS = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "HAJIMI_DEMO_KEY",
    "HAJIMI_HOST",
    "HAJIMI_PORT",
)


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


def _parse_env_dict(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = pattern.match(stripped)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def resolve_l5_root() -> Path | None:
    """Resolve L5 Sidecar root (same priority as scripts/_resolve_l5_root.bat)."""
    from core.paths import resolve_l5_root as _resolve

    root = _resolve()
    if (root / "scripts" / "start_server.bat").is_file():
        return root
    return None


def resolve_l5_env_path() -> Path | None:
    root = resolve_l5_root()
    if not root:
        return None
    return root / "server" / ".env"


def _settings_to_l5_updates(data: dict) -> Dict[str, str]:
    """LLM/模型设置 → Sidecar .env 更新项（用户设置优先）。"""
    llm = data.get("llm") or {}
    updates: Dict[str, str] = {
        "HAJIMI_DEMO_KEY": (data.get("demo_key") or DEFAULT_DEMO_KEY).strip(),
        "HAJIMI_HOST": DEFAULT_L5_HOST,
        "HAJIMI_PORT": str(DEFAULT_L5_PORT),
    }
    if llm.get("api_key"):
        updates["LLM_API_KEY"] = str(llm["api_key"]).strip()
        if llm.get("base_url"):
            updates["LLM_BASE_URL"] = str(llm["base_url"]).strip()
        if llm.get("model"):
            updates["LLM_MODEL"] = str(llm["model"]).strip()
    return updates


def sync_l5_sidecar_env(data: dict | None = None) -> Path | None:
    """Write user model/API settings into server_A/server/.env (L5 Sidecar)."""
    env_path = resolve_l5_env_path()
    if env_path is None:
        return None
    if not data:
        return None

    updates = _settings_to_l5_updates(data)
    if not updates:
        return None

    example_path = env_path.parent / ".env.example"
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
        existing = _parse_env_dict(text)
        # 空设置不覆盖 Sidecar 已有 key（防止清空模型配置）
        for key in _L5_SIDECAR_SYNC_KEYS:
            if key not in updates or not str(updates.get(key, "")).strip():
                val = (existing.get(key) or "").strip()
                if val:
                    updates[key] = val
    elif example_path.is_file():
        text = example_path.read_text(encoding="utf-8")
    else:
        text = ""

    if not updates.get("LLM_PROVIDER"):
        updates["LLM_PROVIDER"] = "deepseek"

    lines = _parse_env_lines(text)
    merged = _upsert_env_lines(lines, updates)
    content = "\n".join(merged).rstrip() + "\n"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = env_path.with_suffix(".env.l5sync.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, env_path)
    print(f"[L5] synced Sidecar env -> {env_path}")
    return env_path
