# [VERIFY] 验收脚本 — 见 docs/FILE-MAP.md
# 用途: 模型/主题分块保存、avatar 持久化、表单解耦、透明度三方案
# 运行: python scripts/verify_settings_fragment.py
"""Verify split settings save, avatar persistence, and appearance/model decoupling."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtWidgets import QApplication

from core import user_settings as us
from ui.native.orange_cat.image_pool import (
    apply_avatar_settings,
    default_ai_avatar_path,
    set_ai_avatar_path,
)
from ui.native.settings_widgets import UiAppearanceGroup
from ui.native.shell_appearance import (
    SCHEME_DEFAULT_BLUE,
    SCHEME_ELEGANT_BLACK,
    SCHEME_KRAFT_PAPER,
    SCHEME_LUXURY_GOLD,
    SCHEME_ORANGE_CAT,
)


def _with_temp_settings_file(fn) -> None:
    """Run fn while redirecting user_settings to a temp JSON file."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "HAJIMI")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "user_settings.json")
        old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = tmp
        try:
            seed = deepcopy(us.DEFAULT_SETTINGS)
            seed["ui_theme"] = "current"
            seed["font_size"] = 15
            seed["a_end_url"] = "http://127.0.0.1:8010"
            seed["llm"] = {**seed["llm"], "api_key": "seed-key", "model": "seed-model"}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(seed, f)
            fn(path)
        finally:
            if old is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old


def _check_split_save_merge() -> None:
    def run(_path: str) -> None:
        base = us.load_user_settings()
        assert base.get("font_size") == 15
        assert base.get("llm", {}).get("api_key") == "seed-key"

        model_frag = {
            "deployment_mode": "gpu_api",
            "a_end_url": "http://127.0.0.1:9999",
            "demo_key": "new-demo",
            "routing_mode": "fast",
            "llm_speed_mode": "fast",
            "llm": {"base_url": "https://x/v1", "api_key": "new-key", "model": "new-model"},
            "omniparser": {"url": "http://omni", "gpu_url": ""},
            "l4": {
                "planner_model": "p",
                "locator_model": "l",
                "planner_use_vision": False,
                "strict_locate": True,
                "pipeline_enabled": True,
            },
        }
        after_model = us.save_settings_fragment(model_frag)
        assert after_model.get("font_size") == 15, "model save must not wipe appearance"
        assert after_model.get("ui_theme") == base.get("ui_theme")
        assert after_model.get("a_end_url") == "http://127.0.0.1:9999"
        assert after_model.get("llm", {}).get("api_key") == "new-key"

        appearance_frag = {
            "ui_theme": "variant_orange_cat",
            "font_size": 14,
            "orange_cat_ai_avatar": "/tmp/test-ai.png",
            "orange_cat_user_avatar": "/tmp/test-user.png",
        }
        after_appearance = us.save_settings_fragment(appearance_frag)
        assert after_appearance.get("a_end_url") == "http://127.0.0.1:9999", (
            "appearance save must not wipe model"
        )
        assert after_appearance.get("llm", {}).get("api_key") == "new-key"
        assert after_appearance.get("font_size") == 14
        assert after_appearance.get("orange_cat_ai_avatar") == "/tmp/test-ai.png"

        voice_frag = {
            "voice": {
                "tts_enabled": False,
                "asr_enabled": True,
                "tts_speed": 0.75,
                "tts_engine": "pyttsx3",
                "asr_engine": "vosk",
            }
        }
        after_voice = us.save_settings_fragment(voice_frag)
        assert after_voice.get("a_end_url") == "http://127.0.0.1:9999", (
            "voice save must not wipe model"
        )
        assert after_voice.get("font_size") == 14, "voice save must not wipe appearance"
        assert after_voice.get("voice", {}).get("tts_enabled") is False
        assert after_voice.get("voice", {}).get("tts_speed") == 0.75

    _with_temp_settings_file(run)


def _check_collect_decoupling(app: QApplication) -> None:
    from ui.native.medium_panel import MediumPanel

    panel = MediumPanel()
    panel.load_settings_form()
    panel._field_llm_model.set_text("form-model-xyz")
    panel._appearance_group._font_size_slider.setValue(14)

    model_data = panel._collect_model_settings()
    appearance_data = panel._collect_appearance_settings()

    assert "font_size" not in model_data, "model collect must not read appearance form"
    assert model_data.get("llm", {}).get("model") == "form-model-xyz"
    assert appearance_data.get("font_size") == 14
    assert "a_end_url" not in appearance_data, "appearance collect must not read model form"
    assert "llm" not in appearance_data

    voice_data = panel._voice_group.current_voice()
    assert "tts_enabled" in voice_data
    assert "a_end_url" not in voice_data

    panel._field_llm_model.set_text("changed-but-not-saved")
    panel._appearance_group._font_size_slider.setValue(12)
    panel._appearance_group.set_scheme(SCHEME_ORANGE_CAT)
    preview = panel._appearance_group.current_appearance()
    assert preview.get("font_size") == 12
    assert panel._field_llm_model.text() == "changed-but-not-saved"
    model_again = panel._collect_model_settings()
    assert model_again.get("llm", {}).get("model") == "changed-but-not-saved"


def _check_alpha_scheme_visibility(app: QApplication) -> None:
    group = UiAppearanceGroup()

    def alpha_shown() -> bool:
        return not group._classic_alpha_section.isHidden()

    for scheme in (SCHEME_DEFAULT_BLUE, SCHEME_ELEGANT_BLACK, SCHEME_ORANGE_CAT):
        group.set_scheme(scheme)
        group.sync_scheme_sections()
        assert alpha_shown(), f"alpha must show for {scheme}"

    for scheme in (SCHEME_LUXURY_GOLD, SCHEME_KRAFT_PAPER):
        group.set_scheme(scheme)
        group.sync_scheme_sections()
        assert group._classic_alpha_section.isHidden(), f"alpha must hide for {scheme}"


def _check_avatar_injection() -> None:
    set_ai_avatar_path("")
    apply_avatar_settings(
        {
            "orange_cat_ai_avatar": "/nonexistent/path.png",
            "orange_cat_user_avatar": "",
        }
    )
    assert default_ai_avatar_path() is None or os.path.isfile(default_ai_avatar_path() or "")


def main() -> int:
    _check_split_save_merge()
    _check_avatar_injection()

    app = QApplication.instance() or QApplication(sys.argv)
    _check_collect_decoupling(app)
    _check_alpha_scheme_visibility(app)

    print("verify_settings_fragment: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
