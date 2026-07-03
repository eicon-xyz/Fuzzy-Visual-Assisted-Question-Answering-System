"""Load and apply native UI theme packages (QSS + optional shell renderer)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from PyQt5.QtWidgets import QApplication, QWidget

from ui.native.fonts import apply_app_font
from ui.native.shell_appearance import (
    AppearanceSettings,
    appearance_override_qss,
    apply_crystal_drop_shadow,
    is_crystal_shell,
)
from ui.native.shell_renderer import apply_shell_renderer

ShellMode = Literal["qss", "crystal"]

_THEMES_DIR = os.path.join(os.path.dirname(__file__), "themes")
_SHELL_CRYSTAL_FALLBACK = os.path.join(_THEMES_DIR, "current", "shell_crystal.qss")

THEME_IDS = ("current", "variant_b", "variant_c")

THEME_LABELS = {
    "current": "默认（工程基线）",
    "variant_b": "变体 B（Stitch 占位）",
    "variant_c": "变体 C（Stitch 占位）",
}


@dataclass(frozen=True)
class ThemeProfile:
    theme_id: str
    shell_mode: ShellMode


THEME_PROFILES: dict[str, ThemeProfile] = {
    "current": ThemeProfile("current", "qss"),
    "variant_b": ThemeProfile("variant_b", "qss"),
    "variant_c": ThemeProfile("variant_c", "qss"),
}


def _read_qss(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _transparent_shell_qss(theme_id: str) -> str:
    """Always load transparent shell QSS — never fallback to opaque shell.qss."""
    theme_path = os.path.join(_THEMES_DIR, theme_id, "shell_crystal.qss")
    if os.path.isfile(theme_path):
        return _read_qss(theme_path)
    return _read_qss(_SHELL_CRYSTAL_FALLBACK)


def compose_stylesheet(
    theme_id: str,
    appearance: AppearanceSettings | None = None,
) -> str:
    """Concatenate _base + transparent shell + topbar/content QSS + appearance overrides."""
    if theme_id not in THEME_IDS:
        theme_id = "current"
    appearance = appearance or AppearanceSettings()
    theme_dir = os.path.join(_THEMES_DIR, theme_id)
    parts = [
        _read_qss(os.path.join(_THEMES_DIR, "_base.qss")),
        _transparent_shell_qss(theme_id),
        _read_qss(os.path.join(theme_dir, "topbar.qss")),
        _read_qss(os.path.join(theme_dir, "content.qss")),
        appearance_override_qss(appearance),
    ]
    return "\n\n".join(p for p in parts if p.strip())


def _repolish_subtree(root: QWidget) -> None:
    style = root.style()
    style.unpolish(root)
    style.polish(root)
    for child in root.findChildren(QWidget):
        style.unpolish(child)
        style.polish(child)
        child.update()


class ThemeManager:
    """Apply theme stylesheet and shell renderer to registered panels."""

    def __init__(self, app: QApplication):
        self._app = app
        self._shells: list[tuple[QWidget, bool]] = []
        self._theme_id = "current"
        self._appearance = AppearanceSettings()

    @property
    def theme_id(self) -> str:
        return self._theme_id

    @property
    def appearance(self) -> AppearanceSettings:
        return self._appearance

    def register_shell(self, widget: QWidget, *, compact: bool = False) -> None:
        for existing, _ in self._shells:
            if existing is widget:
                return
        self._shells.append((widget, compact))

    def apply(
        self,
        theme_id: str | None = None,
        appearance: AppearanceSettings | None = None,
    ) -> str:
        tid = theme_id if theme_id in THEME_IDS else self._theme_id
        if theme_id in THEME_IDS:
            self._theme_id = theme_id
        if appearance is not None:
            self._appearance = appearance

        stylesheet = compose_stylesheet(self._theme_id, self._appearance)
        self._app.setStyleSheet(stylesheet)
        apply_app_font(self._app, size=self._appearance.font_size)

        for widget, compact in self._shells:
            if is_crystal_shell(self._appearance.shell_style):
                apply_shell_renderer(
                    widget,
                    "crystal",
                    compact=compact,
                    appearance=self._appearance,
                )
                apply_crystal_drop_shadow(
                    widget, self._appearance.crystal_shadow_strength
                )
            else:
                apply_shell_renderer(
                    widget,
                    "qss",
                    compact=compact,
                    appearance=self._appearance,
                )
            _repolish_subtree(widget)
            widget.repaint()

        self._app.processEvents()
        return self._theme_id


def get_theme_manager(app: QApplication | None = None) -> ThemeManager:
    """Return the singleton ThemeManager bound to the QApplication."""
    instance = app or QApplication.instance()
    if instance is None:
        raise RuntimeError("QApplication must exist before ThemeManager")
    mgr = getattr(instance, "_hajimi_theme_manager", None)
    if mgr is None:
        mgr = ThemeManager(instance)
        instance._hajimi_theme_manager = mgr  # type: ignore[attr-defined]
    return mgr
