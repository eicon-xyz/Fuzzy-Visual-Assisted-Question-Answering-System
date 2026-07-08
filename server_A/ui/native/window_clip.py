"""Rounded window mask and screen geometry clamping for frameless shell."""
from __future__ import annotations

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QPainterPath, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from ui.native.layout_tokens import SHELL_RADIUS

SHELL_CLIP_RADIUS = SHELL_RADIUS


def available_geometry() -> QRect:
    screen = QApplication.primaryScreen()
    if not screen:
        return QRect(0, 0, 1920, 1080)
    return screen.availableGeometry()


def clamp_geometry_to_screen(geo: QRect) -> QRect:
    """Keep window fully inside the primary screen available area."""
    area = available_geometry()
    w = min(geo.width(), area.width())
    h = min(geo.height(), area.height())
    w = max(1, w)
    h = max(1, h)

    x = geo.x()
    y = geo.y()

    if x < area.left():
        x = area.left()
    if y < area.top():
        y = area.top()
    if x + w > area.right() + 1:
        x = area.right() + 1 - w
    if y + h > area.bottom() + 1:
        y = area.bottom() + 1 - h

    x = max(area.left(), min(x, area.right() + 1 - w))
    y = max(area.top(), min(y, area.bottom() + 1 - h))
    return QRect(int(x), int(y), int(w), int(h))


def apply_shell_mask(
    widget: QWidget,
    *,
    pill: bool = False,
    radius: int = SHELL_RADIUS,
) -> None:
    """Clip frameless host window to rounded rect or pill shape.

    Pill mode is only valid when the host is at compact settled geometry
    (caller should gate on compact mode + height ~ COMPACT_HEIGHT).
    """
    w, h = widget.width(), widget.height()
    if w <= 0 or h <= 0:
        return
    if pill:
        r = max(0, min(w // 2, h // 2))
    else:
        r = max(0, min(radius, w // 2, h // 2))
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, r, r)
    widget.setMask(QRegion(path.toFillPolygon().toPolygon()))


def apply_rounded_mask(widget: QWidget, radius: int = SHELL_CLIP_RADIUS) -> None:
    """Clip frameless host window to rounded rect (medium panel)."""
    apply_shell_mask(widget, pill=False, radius=radius)
