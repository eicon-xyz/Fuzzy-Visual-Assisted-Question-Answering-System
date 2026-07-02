"""Shell background renderer — QSS vs QPainter crystal (mutually exclusive)."""
from __future__ import annotations

from typing import Callable, Literal

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget

from ui.native.crystal_glass import (
    DEFAULT_CRYSTAL_SHADOW,
    ShadowProfile,
    paint_crystal_glass,
)
from ui.native.widgets import apply_shell_shadow

ShellMode = Literal["qss", "crystal"]

_ORIGINAL_PAINT_ATTR = "_hajimi_original_paintEvent"
_SHELL_MODE_ATTR = "_hajimi_shell_mode"
_SHELL_COMPACT_ATTR = "_hajimi_shell_compact"
_CRYSTAL_SHADOW_ATTR = "_hajimi_crystal_shadow"
_CRYSTAL_FILL_ALPHA_ATTR = "_hajimi_crystal_fill_alpha"


def _crystal_paint_event(widget: QWidget, event):
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing, True)
    compact = bool(widget.property(_SHELL_COMPACT_ATTR))
    shadow = widget.property(_CRYSTAL_SHADOW_ATTR) or DEFAULT_CRYSTAL_SHADOW
    fill_alpha = widget.property(_CRYSTAL_FILL_ALPHA_ATTR)
    if fill_alpha is not None:
        fill_alpha = int(fill_alpha)
    paint_crystal_glass(
        painter,
        float(widget.width()),
        float(widget.height()),
        compact=compact,
        shadow=shadow,
        fill_alpha=fill_alpha,
    )
    painter.end()
    QWidget.paintEvent(widget, event)


def _restore_default_paint(widget: QWidget) -> None:
    original = getattr(widget, _ORIGINAL_PAINT_ATTR, None)
    if original is not None:
        widget.paintEvent = original  # type: ignore[method-assign]
        delattr(widget, _ORIGINAL_PAINT_ATTR)


def _install_custom_paint(widget: QWidget, handler: Callable) -> None:
    if not hasattr(widget, _ORIGINAL_PAINT_ATTR):
        widget._hajimi_original_paintEvent = widget.paintEvent  # type: ignore[attr-defined]
    widget.paintEvent = handler.__get__(widget, type(widget))  # type: ignore[method-assign]


def apply_shell_renderer(
    widget: QWidget,
    mode: ShellMode,
    *,
    compact: bool = False,
    shadow: ShadowProfile = DEFAULT_CRYSTAL_SHADOW,
    fill_alpha: int | None = None,
) -> None:
    """Apply shell drawing mode. QSS and crystal are mutually exclusive."""
    prev_mode = widget.property(_SHELL_MODE_ATTR)
    widget.setProperty(_SHELL_COMPACT_ATTR, compact)
    widget.setProperty(_CRYSTAL_SHADOW_ATTR, shadow)
    widget.setProperty(_CRYSTAL_FILL_ALPHA_ATTR, fill_alpha)

    if mode == "qss":
        if prev_mode == "crystal":
            _restore_default_paint(widget)
        widget.setProperty(_SHELL_MODE_ATTR, mode)
        widget.setAttribute(Qt.WA_StyledBackground, True)
        widget.setAttribute(Qt.WA_TranslucentBackground, False)
        if widget.graphicsEffect() is None:
            apply_shell_shadow(widget)
        widget.update()
        return

    if prev_mode != "crystal":
        widget.setGraphicsEffect(None)
        widget.setAttribute(Qt.WA_StyledBackground, True)
        widget.setAttribute(Qt.WA_TranslucentBackground, True)
        _install_custom_paint(widget, _crystal_paint_event)
    widget.setProperty(_SHELL_MODE_ATTR, mode)
    widget.update()
