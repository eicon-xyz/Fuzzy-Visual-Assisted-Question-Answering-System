"""用户系统设置持久化（L5 自动执行模式 + 模型 key + 外观 + 语音）。

L4 指引模式相关字段（deployment_mode / a_end_url / omniparser / l4 /
routing_mode / llm_speed_mode）已随 L4 移除；模型设置只同步到
server_A L5 Sidecar 的 server/.env。
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Dict

from core.defaults import (
    DEFAULT_DEMO_KEY,
    DEFAULT_VOICE_SETTINGS,
)

DEFAULT_SETTINGS: Dict[str, Any] = {
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
    "orange_cat_splash_audio": "",
    "orange_cat_ai_avatar": "",
    "orange_cat_user_avatar": "",
    "demo_key": DEFAULT_DEMO_KEY,
    "llm": {
        # 留空 = 使用 server_A/server/.env 中已有配置（DEEPSEEK_API_KEY 等）
        "base_url": "",
        "api_key": "",
        "model": "deepseek-chat",
    },
    "l5_consent_accepted": False,
    "l5_desktop_overlay": True,
    "shortcut_l5_approve": "H",
    "shortcut_l5_stop": "J",
    "shortcut_l5_pause": "P",
    "voice": dict(DEFAULT_VOICE_SETTINGS),
    "proxy_enabled": False,
    "http_proxy": "http://127.0.0.1:7890",
    "https_proxy": "http://127.0.0.1:7890",
}

_LOCAL_NO_PROXY = "127.0.0.1,localhost,::1"


def _settings_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "HAJIMI")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "user_settings.json")


def _merge_core_settings(out: dict, data: dict) -> None:
    if "l5_consent_accepted" in data:
        out["l5_consent_accepted"] = bool(data["l5_consent_accepted"])
    if "l5_desktop_overlay" in data:
        out["l5_desktop_overlay"] = bool(data["l5_desktop_overlay"])
    for key in ("shortcut_l5_approve", "shortcut_l5_stop", "shortcut_l5_pause"):
        if data.get(key):
            val = str(data[key]).strip().upper()
            if val:
                out[key] = val[:1]
    if data.get("demo_key"):
        out["demo_key"] = str(data["demo_key"]).strip()
    if "proxy_enabled" in data:
        out["proxy_enabled"] = bool(data["proxy_enabled"])
    for key in ("http_proxy", "https_proxy"):
        if key in data and data[key] is not None:
            out[key] = str(data[key]).strip()
    llm = data.get("llm") or {}
    if isinstance(llm, dict):
        for k in ("base_url", "api_key", "model"):
            if llm.get(k) is not None:
                out["llm"][k] = str(llm[k]).strip()
    voice = data.get("voice") or {}
    if isinstance(voice, dict):
        _merge_voice_settings(out["voice"], voice)


def _merge_voice_settings(out: dict, data: dict) -> None:
    for key in ("tts_enabled", "asr_enabled"):
        if key in data:
            out[key] = bool(data[key])
    if "tts_speed" in data:
        try:
            out["tts_speed"] = max(0.5, min(1.5, float(data["tts_speed"])))
        except (TypeError, ValueError):
            pass
    for key in ("tts_engine", "asr_engine", "asr_language", "vosk_model_path"):
        if data.get(key):
            out[key] = str(data[key]).strip()
    if out.get("asr_engine") == "baidu":
        out["asr_engine"] = "vosk"
    if "microphone_index" in data:
        raw = data["microphone_index"]
        if raw is None or raw == "":
            out["microphone_index"] = None
        else:
            try:
                idx = int(raw)
                out["microphone_index"] = idx if idx >= 0 else None
            except (TypeError, ValueError):
                pass
    for key in ("asr_silence_sec", "asr_start_timeout_sec"):
        if key in data:
            try:
                val = float(data[key])
                if key == "asr_silence_sec":
                    out[key] = max(1.0, min(15.0, val))
                else:
                    out[key] = max(3.0, min(30.0, val))
            except (TypeError, ValueError):
                pass
    if "config_pull_interval_min" in data:
        try:
            out["config_pull_interval_min"] = max(
                5, int(data["config_pull_interval_min"])
            )
        except (TypeError, ValueError):
            pass


def _merge_ui_settings(out: dict, data: dict) -> None:
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

    if data.get("ui_theme") in (
        "current",
        "variant_luxury",
        "variant_orange_cat",
    ):
        out["ui_theme"] = data["ui_theme"]
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
    if "orange_cat_splash_audio" in data:
        out["orange_cat_splash_audio"] = str(data.get("orange_cat_splash_audio") or "").strip()
    if "orange_cat_ai_avatar" in data:
        out["orange_cat_ai_avatar"] = str(data.get("orange_cat_ai_avatar") or "").strip()
    if "orange_cat_user_avatar" in data:
        out["orange_cat_user_avatar"] = str(data.get("orange_cat_user_avatar") or "").strip()


def _merge_ui_settings_headless(out: dict, data: dict) -> None:
    """Copy UI keys without PyQt when running headless setup scripts."""
    for key, default in DEFAULT_SETTINGS.items():
        if key in ("demo_key", "llm"):
            continue
        if key not in data:
            continue
        val = data[key]
        if isinstance(default, dict) and isinstance(val, dict):
            out[key] = {**default, **val}
        else:
            out[key] = val


def _merge_defaults(data: dict) -> dict:
    out = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(data, dict):
        return out
    try:
        from ui.native.shell_appearance import migrate_appearance_settings

        data = migrate_appearance_settings(data)
    except ImportError:
        pass
    _merge_core_settings(out, data)
    try:
        _merge_ui_settings(out, data)
    except ImportError:
        _merge_ui_settings_headless(out, data)
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


def _deep_merge_fragment(base: dict, fragment: dict) -> dict:
    """Merge fragment onto disk snapshot; nested llm/voice are deep-merged."""
    out = deepcopy(base)
    for key, val in fragment.items():
        if key in ("llm", "voice") and isinstance(val, dict):
            nested = out.get(key)
            if not isinstance(nested, dict):
                nested = {}
            out[key] = {**nested, **val}
        else:
            out[key] = val
    return out


def load_voice_settings() -> dict:
    """返回当前语音设置副本（B↔C 共享状态）。"""
    voice = load_user_settings().get("voice") or {}
    return {**DEFAULT_VOICE_SETTINGS, **voice}


def save_settings_fragment(fragment: dict) -> dict:
    """Write only the given keys, preserving other fields already on disk."""
    base = load_user_settings()
    combined = _deep_merge_fragment(base, fragment)
    return save_user_settings(combined)


def save_user_settings(data: dict) -> dict:
    merged = _merge_defaults(data)
    path = _settings_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return merged


def _apply_proxy_environ(settings: dict) -> None:
    """仅影响当前 B 进程：启用时写 HTTP(S)_PROXY，并强制本机 NO_PROXY。"""
    if settings.get("proxy_enabled"):
        http_p = (settings.get("http_proxy") or "").strip()
        https_p = (settings.get("https_proxy") or "").strip() or http_p
        if http_p:
            os.environ["HTTP_PROXY"] = http_p
            os.environ["http_proxy"] = http_p
        if https_p:
            os.environ["HTTPS_PROXY"] = https_p
            os.environ["https_proxy"] = https_p
        os.environ["NO_PROXY"] = _LOCAL_NO_PROXY
        os.environ["no_proxy"] = _LOCAL_NO_PROXY
    else:
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
            "NO_PROXY",
            "no_proxy",
        ):
            os.environ.pop(key, None)


def apply_user_settings(data: dict | None = None) -> dict:
    """写入 os.environ 并刷新 config / api_client 模块变量。"""
    settings = _merge_defaults(data) if data is not None else load_user_settings()

    os.environ["HAJIMI_DEMO_KEY"] = settings["demo_key"]

    _apply_proxy_environ(settings)

    # L5 Sidecar 固定本机 :8011
    os.environ["L5_API_URL"] = "http://127.0.0.1:8011"
    try:
        from core.paths import resolve_l5_root

        l5_root = resolve_l5_root()
        if l5_root.is_dir():
            os.environ["HAJIMI_L5_ROOT"] = str(l5_root)
    except Exception:
        pass

    import config as client_config

    client_config.reload_from_env()

    try:
        import core.api_client as api_client

        api_client.reload_client_config()
    except Exception:
        pass

    return settings
