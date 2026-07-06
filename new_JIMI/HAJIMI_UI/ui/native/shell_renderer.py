"""Shell background renderer — QSS vs QPainter crystal (mutually exclusive)."""
from __future__ import annotations

from typing import Literal

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget

from ui.native.layout_tokens import SHELL_RADIUS
from ui.native.luxury.paint import paint_luxury_frame
from ui.native.luxury.qss import LUXURY_SHELL_RADIUS
from ui.native.shell_appearance import (
    AppearanceSettings,
    crystal_fill_alpha_from_percent,
    qss_rgba_from_percent,
)
from ui.native.shell_paint import paint_crystal_shell, paint_qss_shell
from ui.native.widgets import apply_shell_shadow

ShellMode = Literal["qss", "crystal", "luxury"]

_ORIGINAL_PAINT_ATTR = "_hajimi_original_paintEvent"
_SHELL_MODE_ATTR = "_hajimi_shell_mode"
_SHELL_COMPACT_ATTR = "_hajimi_shell_compact"
_APPEARANCE_ATTR = "_hajimi_shell_appearance"


def _shell_radius(compact: bool, height: float, *, mode: str = "", width: float = 0) -> float:
    if compact:
        w = width if width > 0 else height
        return min(height / 2, w / 2)
    if mode == "luxury":
        return float(LUXURY_SHELL_RADIUS)
    return float(SHELL_RADIUS)


def _shell_paint_event(widget: QWidget, event):
    appearance = getattr(widget, _APPEARANCE_ATTR, None)
    if not isinstance(appearance, AppearanceSettings):
        QWidget.paintEvent(widget, event)
        return

    mode = str(getattr(widget, _SHELL_MODE_ATTR, "") or "")
    compact = bool(getattr(widget, _SHELL_COMPACT_ATTR, False))
    w = float(widget.width())
    h = float(widget.height())
    if w <= 0 or h <= 0:
        return

    radius = _shell_radius(compact, h, mode=mode, width=w)
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing, True)

    if mode == "crystal":
        alpha_pct = (
            appearance.shell_alpha_compact if compact else appearance.shell_alpha_medium
        )
        paint_crystal_shell(
            painter,
            w,
            h,
            radius=radius,
            compact=compact,
            fill_alpha=crystal_fill_alpha_from_percent(alpha_pct),
            light_mode=appearance.top_light_mode,  # type: ignore[arg-type]
            top_light_peak=appearance.top_light_peak,
        )
    elif mode == "luxury":
        paint_luxury_frame(
            painter,
            QRectF(0, 0, w, h),
            bg_mode=appearance.luxury_bg_mode,  # type: ignore[arg-type]
            shell_mode="SA",
            star_intensity=appearance.luxury_star_intensity,
            radius=radius,
            compact=compact,
        )
    else:
        alpha_pct = (
            appearance.shell_alpha_compact if compact else appearance.shell_alpha_medium
        )
        paint_qss_shell(
            painter,
            w,
            h,
            rgba=qss_rgba_from_percent(alpha_pct),
            body_mode=appearance.qss_body_mode,  # type: ignore[arg-type]
            highlight_mode=appearance.qss_highlight_mode,  # type: ignore[arg-type]
            highlight_peak=appearance.qss_highlight_peak,
            radius=radius,
            compact=compact,
        )
    painter.end()


def _refresh_shell_stylesheet(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _ensure_custom_paint(widget: QWidget) -> None:
    if not hasattr(widget, _ORIGINAL_PAINT_ATTR):
        widget._hajimi_original_paintEvent = widget.paintEvent  # type: ignore[attr-defined]
    widget.paintEvent = _shell_paint_event.__get__(widget, type(widget))  # type: ignore[method-assign]


def apply_shell_renderer(
    widget: QWidget,
    mode: ShellMode,
    *,
    compact: bool = False,
    appearance: AppearanceSettings | None = None,
) -> None:
    """Apply shell drawing mode. QSS and crystal both use QPainter + DropShadow."""
    appearance = appearance or AppearanceSettings()
    setattr(widget, _APPEARANCE_ATTR, appearance)
    setattr(widget, _SHELL_COMPACT_ATTR, compact)
    setattr(widget, _SHELL_MODE_ATTR, mode)

    _ensure_custom_paint(widget)
    widget.setAutoFillBackground(False)
    widget.setAttribute(Qt.WA_StyledBackground, False)

    if mode == "qss":
        widget.setAttribute(Qt.WA_TranslucentBackground, False)
        widget.setGraphicsEffect(None)
        if not compact:
            apply_shell_shadow(widget)
    else:
        widget.setAttribute(Qt.WA_TranslucentBackground, True)
        if mode == "luxury":
            widget.setGraphicsEffect(None)

    _refresh_shell_stylesheet(widget)
    widget.repaint()
