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
from ui.native.shell_appearance import AppearanceSettings
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
    for tid in ("current", "variant_b", "variant_c"):
        _check_theme(tid, "qss")
        _check_theme(tid, "crystal_light")

    luxury_merged = _merge_defaults({"ui_theme": "variant_luxury"})
    luxury_qss = compose_stylesheet(
        "variant_luxury",
        AppearanceSettings.from_user_settings(luxury_merged),
    )
    assert "SendBtnLuxHover" in luxury_qss
    assert "border-radius: 10px" in luxury_qss
    assert "#NavDrawer" in luxury_qss
    assert "background: transparent" in luxury_qss or "background-color: transparent" in luxury_qss

    merged = _merge_defaults({"ui_theme": "variant_b", "shell_style": "crystal_light"})
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
    assert panel._title_art._accent == accent_for_theme("variant_b")

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

    print("verify_theme_apply: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
