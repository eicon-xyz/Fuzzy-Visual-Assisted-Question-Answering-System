"""Assist 层配置 — 默认关闭以保持 L4/L3 回归行为不变。"""
import os


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


ASSIST_ENABLED = _env_bool("ASSIST_ENABLED", False)
ASSIST_UIA_ENABLED = _env_bool("ASSIST_UIA_ENABLED", True)
ASSIST_DESKTOP_SHORTCUTS = _env_bool("ASSIST_DESKTOP_SHORTCUTS", True)
ASSIST_BROWSER_ENABLED = _env_bool("ASSIST_BROWSER_ENABLED", True)
ASSIST_WPS_ENABLED = _env_bool("ASSIST_WPS_ENABLED", True)
ASSIST_ROI_VISION_FALLBACK = _env_bool("ASSIST_ROI_VISION_FALLBACK", True)

try:
    ASSIST_HYBRID_MIN_CONFIDENCE = float(os.getenv("ASSIST_HYBRID_MIN_CONFIDENCE", "0.72"))
except ValueError:
    ASSIST_HYBRID_MIN_CONFIDENCE = 0.72
