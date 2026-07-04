"""用户系统设置持久化（部署模式 + API 配置）。"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Dict

from core.defaults import DEFAULT_A_URL, DEFAULT_DEMO_KEY, DEFAULT_OMNI_LOCAL_URL

DEFAULT_SETTINGS: Dict[str, Any] = {
    "deployment_mode": "local",
    "ui_theme": "current",
    "shell_style": "qss",
    "shell_alpha_medium": 89,
    "shell_alpha_compact": 89,
    "font_size": 13,
    "crystal_shadow_strength": 0,
    "title_art_mode": "gradient",
    "top_light_mode": "dual",
    "top_light_peak": 34,
    "qss_body_mode": "solid",
    "qss_highlight_mode": "dual_lite",
    "qss_highlight_peak": 34,
    "luxury_bg_mode": "frosted",
    "luxury_star_intensity": 0,
    "luxury_script_font_id": "mrs_delafield",
    "luxury_gold_mode": "dual_layer",
    "luxury_btn_mode": "hover",
    "a_end_url": DEFAULT_A_URL,
    "demo_key": DEFAULT_DEMO_KEY,
    "llm": {
        "base_url": "https://api.deepseek.com",
        "api_key": "",
        "model": "deepseek-chat",
    },
    "omniparser": {
        "url": DEFAULT_OMNI_LOCAL_URL,
        "gpu_url": "",
    },
}


def _settings_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "HAJIMI")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "user_settings.json")


def _merge_defaults(data: dict) -> dict:
    out = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(data, dict):
        return out
    if data.get("deployment_mode") in ("local", "intranet"):
        out["deployment_mode"] = data["deployment_mode"]
    if data.get("ui_theme") in ("current", "variant_b", "variant_c", "variant_luxury"):
        out["ui_theme"] = data["ui_theme"]
    from ui.native.shell_appearance import (
        DEFAULT_FONT_SIZE,
        DEFAULT_LUXURY_BG_MODE,
        DEFAULT_LUXURY_STAR_INTENSITY,
        DEFAULT_SHELL_ALPHA_COMPACT,
        DEFAULT_SHELL_ALPHA_MEDIUM,
        DEFAULT_SHELL_STYLE,
        FONT_SIZE_MAX,
        FONT_SIZE_MIN,
        LUXURY_BG_MODE_IDS,
        LUXURY_STAR_INTENSITY_MAX,
        SHADOW_STRENGTH_MAX,
        SHELL_ALPHA_MAX,
        SHELL_ALPHA_MIN,
        SHELL_STYLE_IDS,
        default_crystal_shadow_strength,
    )
    from ui.native.luxury.qss import DEFAULT_LUXURY_BTN_MODE, DEFAULT_LUXURY_GOLD_MODE
    from ui.native.luxury.title import DEFAULT_SCRIPT_FONT_ID, LUXURY_SCRIPT_FONT_IDS
    from ui.native.shell_paint import (
        DEFAULT_LIGHT_MODE,
        DEFAULT_QSS_BODY,
        DEFAULT_QSS_HIGHLIGHT,
        DEFAULT_QSS_HIGHLIGHT_PEAK,
        DEFAULT_TOP_LIGHT_PEAK,
        LIGHT_MODE_IDS,
        QSS_BODY_MODE_IDS,
        QSS_HIGHLIGHT_MODE_IDS,
    )
    from ui.native.title_art import DEFAULT_TITLE_ART, TITLE_ART_MODE_IDS

    shell_style = data.get("shell_style", DEFAULT_SHELL_STYLE)
    if shell_style in SHELL_STYLE_IDS:
        out["shell_style"] = shell_style
    out["shell_alpha_medium"] = max(
        SHELL_ALPHA_MIN,
        min(SHELL_ALPHA_MAX, int(data.get("shell_alpha_medium", DEFAULT_SHELL_ALPHA_MEDIUM))),
    )
    out["shell_alpha_compact"] = max(
        SHELL_ALPHA_MIN,
        min(SHELL_ALPHA_MAX, int(data.get("shell_alpha_compact", DEFAULT_SHELL_ALPHA_COMPACT))),
    )
    out["font_size"] = max(
        FONT_SIZE_MIN,
        min(FONT_SIZE_MAX, int(data.get("font_size", DEFAULT_FONT_SIZE))),
    )
    if "crystal_shadow_strength" in data and data.get("crystal_shadow_strength") is not None:
        out["crystal_shadow_strength"] = max(
            0,
            min(SHADOW_STRENGTH_MAX, int(data["crystal_shadow_strength"])),
        )
    else:
        out["crystal_shadow_strength"] = default_crystal_shadow_strength(out["shell_style"])
    title_art = data.get("title_art_mode", DEFAULT_TITLE_ART)
    if title_art == "glass":
        title_art = DEFAULT_TITLE_ART
    if title_art in TITLE_ART_MODE_IDS:
        out["title_art_mode"] = title_art
    top_light_mode = data.get("top_light_mode", DEFAULT_LIGHT_MODE)
    if top_light_mode in LIGHT_MODE_IDS:
        out["top_light_mode"] = top_light_mode
    out["top_light_peak"] = max(
        0,
        min(SHADOW_STRENGTH_MAX, int(data.get("top_light_peak", DEFAULT_TOP_LIGHT_PEAK))),
    )
    qss_body = data.get("qss_body_mode", DEFAULT_QSS_BODY)
    if qss_body in QSS_BODY_MODE_IDS:
        out["qss_body_mode"] = qss_body
    qss_highlight = data.get("qss_highlight_mode", DEFAULT_QSS_HIGHLIGHT)
    if qss_highlight in QSS_HIGHLIGHT_MODE_IDS:
        out["qss_highlight_mode"] = qss_highlight
    out["qss_highlight_peak"] = max(
        0,
        min(SHADOW_STRENGTH_MAX, int(data.get("qss_highlight_peak", DEFAULT_QSS_HIGHLIGHT_PEAK))),
    )
    luxury_bg = data.get("luxury_bg_mode", DEFAULT_LUXURY_BG_MODE)
    if luxury_bg in LUXURY_BG_MODE_IDS:
        out["luxury_bg_mode"] = luxury_bg
    out["luxury_star_intensity"] = max(
        0,
        min(
            LUXURY_STAR_INTENSITY_MAX,
            int(data.get("luxury_star_intensity", DEFAULT_LUXURY_STAR_INTENSITY)),
        ),
    )
    luxury_font = data.get("luxury_script_font_id", DEFAULT_SCRIPT_FONT_ID)
    if luxury_font in LUXURY_SCRIPT_FONT_IDS:
        out["luxury_script_font_id"] = luxury_font
    luxury_gold = data.get("luxury_gold_mode", DEFAULT_LUXURY_GOLD_MODE)
    if luxury_gold in ("horizontal", "diagonal", "dual_layer"):
        out["luxury_gold_mode"] = luxury_gold
    luxury_btn = data.get("luxury_btn_mode", DEFAULT_LUXURY_BTN_MODE)
    if luxury_btn in ("edge", "hover"):
        out["luxury_btn_mode"] = luxury_btn
    for key in ("a_end_url", "demo_key"):
        if data.get(key):
            out[key] = str(data[key]).strip()
    llm = data.get("llm") or {}
    if isinstance(llm, dict):
        for k in ("base_url", "api_key", "model"):
            if llm.get(k) is not None:
                out["llm"][k] = str(llm[k]).strip()
    omni = data.get("omniparser") or {}
    if isinstance(omni, dict):
        for k in ("url", "gpu_url"):
            if omni.get(k) is not None:
                out["omniparser"][k] = str(omni[k]).strip()
    return out


def load_user_settings() -> dict:
    path = _settings_path()
    if not os.path.isfile(path):
        return deepcopy(DEFAULT_SETTINGS)
    try:
        with open(path, encoding="utf-8") as f:
            return _merge_defaults(json.load(f))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return deepcopy(DEFAULT_SETTINGS)


def save_user_settings(data: dict) -> dict:
    merged = _merge_defaults(data)
    path = _settings_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return merged


def apply_user_settings(data: dict | None = None) -> dict:
    """写入 os.environ 并刷新 config / api_client 模块变量。"""
    settings = _merge_defaults(data) if data is not None else load_user_settings()

    os.environ["HAJIMI_DEPLOYMENT_MODE"] = settings["deployment_mode"]
    os.environ["HAJIMI_API_URL"] = settings["a_end_url"]
    os.environ["HAJIMI_DEMO_KEY"] = settings["demo_key"]

    llm = settings.get("llm") or {}
    if llm.get("base_url"):
        os.environ["DEEPSEEK_BASE_URL"] = llm["base_url"]
    if llm.get("api_key"):
        os.environ["DEEPSEEK_API_KEY"] = llm["api_key"]
    if llm.get("model"):
        os.environ["DEEPSEEK_MODEL"] = llm["model"]

    omni = settings.get("omniparser") or {}
    omni_url = (omni.get("url") or DEFAULT_OMNI_LOCAL_URL).strip()
    if omni_url:
        os.environ["OMNIPARSER_LOCAL_URL"] = omni_url
        os.environ["OMNIPARSER_URL"] = omni_url
    gpu_url = (omni.get("gpu_url") or "").strip()
    if gpu_url:
        os.environ["OMNIPARSER_GPU_URL"] = gpu_url
    elif "OMNIPARSER_GPU_URL" in os.environ and not gpu_url:
        os.environ.pop("OMNIPARSER_GPU_URL", None)

    os.environ.setdefault("DETECTOR_BACKEND", "auto")

    import config as client_config

    client_config.reload_from_env()

    try:
        import core.api_client as api_client

        api_client.reload_client_config()
    except Exception:
        pass

    return settings


def is_intranet_mode() -> bool:
    return os.environ.get("HAJIMI_DEPLOYMENT_MODE", "local") == "intranet"
