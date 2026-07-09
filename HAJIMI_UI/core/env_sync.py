"""将 B 端用户设置合并写入 server/.env（本地部署模式）。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict

from core.defaults import (
    DEFAULT_DEMO_KEY,
    DEFAULT_L5_HOST,
    DEFAULT_L5_PORT,
    DEFAULT_OMNI_GPU_API_URL,
    DEFAULT_OMNI_LOCAL_URL,
)

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "server" / ".env"
EXAMPLE_PATH = ROOT / "server" / ".env.example"

_L5_SIDECAR_SYNC_KEYS = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "OMNIPARSER_URL",
    "OMNIPARSER_LOCAL_URL",
    "OMNIPARSER_TIMEOUT",
    "OMNIPARSER_LOCAL_TIMEOUT",
    "OMNIPARSER_RETRY",
    "HAJIMI_DEMO_KEY",
    "HAJIMI_HOST",
    "HAJIMI_PORT",
    "ROUTING_MODE",
    "LLM_SPEED_MODE",
)

_CANONICAL_MIRROR_KEYS = _L5_SIDECAR_SYNC_KEYS


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
    custom = os.environ.get("HAJIMI_L5_ROOT", "").strip()
    if custom:
        root = Path(custom)
        if (root / "scripts" / "start_server.bat").is_file():
            return root

    repo = ROOT.parent
    for candidate in (
        repo / "server_A",
        repo / "server_A" / "server_A",
        repo / "new_JIMI" / "HAJIMI_UI",
    ):
        if (candidate / "scripts" / "start_server.bat").is_file():
            return candidate
    return None


def resolve_l5_env_path() -> Path | None:
    root = resolve_l5_root()
    if not root:
        return None
    return root / "server" / ".env"


def _l5_sidecar_env_updates(data: dict | None) -> Dict[str, str]:
    """Build server_A/server/.env updates — user settings are authoritative."""
    if not data:
        return {}

    updates = _settings_to_env_updates(data)
    # L5 Sidecar (server_A) always binds :8011 locally; a_end_url is for 8010 / intranet.
    updates["HAJIMI_HOST"] = DEFAULT_L5_HOST
    updates["HAJIMI_PORT"] = str(DEFAULT_L5_PORT)

    env_path = resolve_l5_env_path()
    if env_path and env_path.is_file():
        existing = _parse_env_dict(env_path.read_text(encoding="utf-8"))
        for key in _CANONICAL_MIRROR_KEYS:
            if key not in updates or not str(updates.get(key, "")).strip():
                val = (existing.get(key) or "").strip()
                if val:
                    updates[key] = val

    if not updates.get("LLM_PROVIDER"):
        updates["LLM_PROVIDER"] = "deepseek"
    return updates


def routing_needs_legacy_a_end(data: dict | None) -> bool:
    """True when L3/L4 still uses HAJIMI_UI/server on :8010."""
    if not data:
        return False
    routing = (data.get("routing_mode") or data.get("llm_speed_mode") or "l5").lower()
    return routing in ("auto", "fast", "balanced", "precision")


def sync_backend_env(data: dict) -> tuple[Path | None, Path | None]:
    """Primary: server_A L5 .env; optional legacy: HAJIMI_UI/server/.env for L4."""
    l5_path = sync_l5_sidecar_env(data)
    legacy_path = sync_server_env(data) if routing_needs_legacy_a_end(data) else None
    return l5_path, legacy_path


def sync_l5_sidecar_env(data: dict | None = None) -> Path | None:
    """Write user model/API settings into server_A/server/.env (L5 Sidecar)."""
    env_path = resolve_l5_env_path()
    if env_path is None:
        return None

    updates = _l5_sidecar_env_updates(data)
    if not updates:
        return None

    example_path = env_path.parent / ".env.example"
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
    elif example_path.is_file():
        text = example_path.read_text(encoding="utf-8")
    else:
        text = ""

    lines = _parse_env_lines(text)
    merged = _upsert_env_lines(lines, updates)
    content = "\n".join(merged).rstrip() + "\n"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = env_path.with_suffix(".env.l5sync.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, env_path)
    print(f"[L5] synced Sidecar env -> {env_path}")
    return env_path


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
