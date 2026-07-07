# [VERIFY] 验收脚本 — 见 docs/FILE-MAP.md
# 用途: 主题 QSS / 壳层 / 五方案 / 橘猫 apply 链
# 运行: python scripts/verify_theme_apply.py
"""Verify theme apply chain: stylesheet, shell mode, painter, opaque shell guard."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtWidgets import QApplication

from core.user_settings import _merge_defaults
from ui.native.compact_bar import CompactBar
from ui.native.luxury.title import DEFAULT_SCRIPT_FONT_ID, ensure_luxury_fonts
from ui.native.medium_panel import MediumPanel
from ui.native.shell_appearance import (
    AppearanceSettings,
    SCHEME_ELEGANT_BLACK,
    SCHEME_KRAFT_PAPER,
    SCHEME_LUXURY_GOLD,
    SCHEME_ORANGE_CAT,
    is_orange_cat_theme,
    scheme_to_settings,
    settings_to_scheme,
)
from ui.native.orange_cat.tokens import PRIMARY, PRIMARY_DARK
from ui.native.theme_manager import compose_stylesheet, get_theme_manager
from ui.native.visual_tokens import accent_for_theme


def _check_theme(theme_id: str, shell_style: str) -> None:
    appearance = AppearanceSettings.from_user_settings(
        {"ui_theme": theme_id, "shell_style": shell_style}
    )
    qss = compose_stylesheet(theme_id, appearance)
    assert "rgba(15, 23, 42, 0.89)" not in qss, f"{theme_id}: opaque shell in QSS"
    assert "background: transparent" in qss or "background-color: transparent" in qss


def main() -> int:
    _check_theme("current", "qss")
    _check_theme("current", "crystal_edge")

    luxury_merged = _merge_defaults({"ui_theme": "variant_luxury"})
    luxury_qss = compose_stylesheet(
        "variant_luxury",
        AppearanceSettings.from_user_settings(luxury_merged),
    )
    assert "SendBtnLuxHover" in luxury_qss
    assert "border-radius: 10px" in luxury_qss
    assert "#NavDrawer" in luxury_qss
    assert "background: transparent" in luxury_qss or "background-color: transparent" in luxury_qss

    orange_merged = _merge_defaults({"ui_theme": "variant_orange_cat"})
    orange_qss = compose_stylesheet(
        "variant_orange_cat",
        AppearanceSettings.from_user_settings(orange_merged),
    )
    assert "SendBtnOrange" in orange_qss
    assert "#FFFBF7" in orange_qss or "bubble-system" in orange_qss
    assert "rgba(15, 23, 42, 0.89)" not in orange_qss

    migrated = _merge_defaults({"ui_theme": "variant_b", "shell_style": "crystal_light"})
    assert migrated["ui_theme"] == "current"
    assert settings_to_scheme(migrated) == SCHEME_ELEGANT_BLACK

    kraft = scheme_to_settings(SCHEME_KRAFT_PAPER)
    assert kraft["ui_theme"] == "variant_luxury"
    assert kraft["luxury_bg_mode"] == "kraft"
    assert settings_to_scheme(kraft) == SCHEME_KRAFT_PAPER

    merged = _merge_defaults(scheme_to_settings(SCHEME_ELEGANT_BLACK))
    app = QApplication(sys.argv)
    panel = MediumPanel()
    compact = CompactBar()
    mgr = get_theme_manager()
    mgr.register_shell(panel, compact=False)
    mgr.register_shell(compact, compact=True)

    appearance = AppearanceSettings.from_user_settings(merged)
    mgr.apply(merged["ui_theme"], appearance)
    panel.apply_appearance(appearance, ui_theme=merged["ui_theme"])

    mode = getattr(panel, "_hajimi_shell_mode", None)
    assert mode == "crystal", f"expected crystal mode, got {mode!r}"
    assert isinstance(getattr(panel, "_hajimi_shell_appearance", None), AppearanceSettings)
    assert panel.paintEvent.__func__.__name__ == "_shell_paint_event"
    assert panel._title_art._accent == accent_for_theme("current")

    luxury_appearance = AppearanceSettings.from_user_settings(luxury_merged)
    mgr.apply("variant_luxury", luxury_appearance)
    panel.apply_appearance(luxury_appearance, ui_theme="variant_luxury")
    assert getattr(panel, "_hajimi_shell_mode", None) == "luxury"
    assert panel._luxury_theme is True
    assert not panel._title_script.isHidden()
    assert panel._title_art.isHidden()
    ensure_luxury_fonts()
    panel._title_script.set_font_id(DEFAULT_SCRIPT_FONT_ID)
    assert panel._title_script.sizeHint().width() > 0

    mgr.apply("current", AppearanceSettings(shell_style="qss"))
    assert getattr(panel, "_hajimi_shell_mode", None) == "qss"
    panel.apply_appearance(AppearanceSettings(shell_style="qss"), ui_theme="current")
    assert panel._title_script.isHidden()
    assert not panel._title_art.isHidden()
    assert panel._orange_cat_theme is False

    orange_appearance = AppearanceSettings.from_user_settings(orange_merged)
    mgr.apply("variant_orange_cat", orange_appearance)
    panel.apply_appearance(orange_appearance, ui_theme="variant_orange_cat")
    assert getattr(panel, "_hajimi_shell_mode", None) == "orange_cat"
    assert panel._orange_cat_theme is True
    assert panel._luxury_theme is False
    assert panel._title_script.isHidden()
    assert not panel._title_art.isHidden()
    assert panel._title_art._mode == "gradient"
    assert panel._title_art._gradient_start == PRIMARY_DARK
    assert panel._title_art._gradient_end == "#FFD4A3"
    assert panel._title_art._accent == PRIMARY
    compact.apply_orange_cat_theme(True)
    assert is_orange_cat_theme("variant_orange_cat")

    mgr.apply("current", AppearanceSettings(shell_style="qss"))
    panel.apply_appearance(AppearanceSettings(shell_style="qss"), ui_theme="current")
    compact.apply_orange_cat_theme(False)
    assert getattr(panel, "_hajimi_shell_mode", None) == "qss"

    print("verify_theme_apply: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
