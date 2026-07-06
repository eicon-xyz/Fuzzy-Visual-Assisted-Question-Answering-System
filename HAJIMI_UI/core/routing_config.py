"""B 端读取 ROUTING_MODE，判断 process 预检是否需要 OmniParser。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "server" / ".env"

_SPEED_TO_ROUTING = {
    "fast": "fast",
    "balanced": "balanced",
    "precision": "precision",
}


def _read_env_file(key: str) -> str:
    if not ENV_PATH.is_file():
        return ""
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line.strip())
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def get_routing_mode() -> str:
    """优先 server/.env / user_settings routing_mode，其次 llm_speed_mode 映射。"""
    mode = (os.environ.get("ROUTING_MODE") or _read_env_file("ROUTING_MODE") or "").lower()
    if mode in ("auto", "fast", "balanced", "precision", "l5"):
        return mode
    try:
        from core.user_settings import load_user_settings

        data = load_user_settings()
        routing = (data.get("routing_mode") or "").lower()
        if routing in ("auto", "fast", "balanced", "precision", "l5"):
            return routing
        speed = (data.get("llm_speed_mode") or "fast").lower()
        return _SPEED_TO_ROUTING.get(speed, "auto")
    except Exception:
        return "l5"


def is_l5_route(mode: Optional[str] = None) -> bool:
    return (mode or get_routing_mode()).lower() == "l5"


def routing_needs_omniparser(mode: Optional[str] = None) -> bool:
    """precision 模式需要 OmniParser；auto/fast/balanced/l5 的 process 预检不需要。"""
    resolved = (mode or get_routing_mode()).lower()
    return resolved == "precision"
