"""L4 Vision 设置读写（user_settings + server/.env）。"""
from __future__ import annotations

from typing import Any, Dict

from core.routing_config import _read_env_file

DEFAULT_L4: Dict[str, Any] = {
    "planner_model": "",
    "locator_model": "",
    "planner_use_vision": False,
    "strict_locate": True,
    "pipeline_enabled": True,
}


def _env_bool(key: str, default: bool) -> bool:
    raw = (_read_env_file(key) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes")


def read_l4_from_server_env() -> Dict[str, Any]:
    """从 server/.env 读取 L4 配置，供设置页回填。"""
    return {
        "planner_model": _read_env_file("L4_PLANNER_MODEL"),
        "locator_model": _read_env_file("L4_LOCATOR_MODEL"),
        "planner_use_vision": _env_bool("L4_PLANNER_USE_VISION", False),
        "strict_locate": _env_bool("L4_STRICT_LOCATE", True),
        "pipeline_enabled": _env_bool("L4_PIPELINE_ENABLED", True),
    }


def merge_l4_for_display(stored: Dict[str, Any] | None) -> Dict[str, Any]:
    """合并 user_settings 与 server/.env，用于设置页展示。"""
    out = read_l4_from_server_env()
    for key, default in DEFAULT_L4.items():
        out.setdefault(key, default)
    if isinstance(stored, dict):
        for key in DEFAULT_L4:
            if key in stored:
                out[key] = stored[key]
    return out
