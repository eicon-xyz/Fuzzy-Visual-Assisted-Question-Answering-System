"""Shared dark crystal glass QPainter background for native shells."""

from __future__ import annotations

from typing import Literal

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import (
    QPainter,
    QBrush,
    QColor,
    QPen,
    QLinearGradient,
    QRadialGradient,
    QPainterPath,
)

CORNER_RADIUS = 20.0
COMPACT_CORNER_RADIUS = 16.0
GLASS_FILL_RGB = (6, 10, 22)
GLASS_FILL_ALPHA = 165
GLASS_BORDER_ALPHA = 41

ShadowProfile = Literal["none", "light", "full"]
DEFAULT_CRYSTAL_SHADOW: ShadowProfile = "light"


def _panel_path(w: float, h: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), r, r)
    return path


def _inset_panel_path(w: float, h: float, r: float, inset: float = 1.0) -> QPainterPath:
    ir = max(0.0, r - inset)
    path = QPainterPath()
    path.addRoundedRect(QRectF(inset, inset, w - 2 * inset, h - 2 * inset), ir, ir)
    return path


def _corner_wedge_path(w: float, h: float, r: float, left: bool) -> QPainterPath:
    """Upper-left or upper-right wedge for radial corner glow."""
    size = min(w * 0.3, h * 0.3, 120.0)
    path = QPainterPath()
    if left:
        path.addRoundedRect(QRectF(0, 0, size, size), min(r, size / 2), min(r, size / 2))
    else:
        path.addRoundedRect(QRectF(w - size, 0, size, size), min(r, size / 2), min(r, size / 2))
    return path


def _bottom_glow_path(
    w: float, h: float, r: float, start_ratio: float = 0.75, top_r: float = 14.0
) -> QPainterPath:
    y0 = h * start_ratio
    y0 = min(y0, h - r - top_r - 1)
    tr = min(top_r, (h - y0 - r) * 0.35)

    path = QPainterPath()
    path.moveTo(tr, y0)
    path.lineTo(w - tr, y0)
    path.arcTo(QRectF(w - 2 * tr, y0, 2 * tr, 2 * tr), 270, 90)
    path.lineTo(w, h - r)
    path.arcTo(QRectF(w - 2 * r, h - 2 * r, 2 * r, 2 * r), 0, 90)
    path.lineTo(r, h)
    path.arcTo(QRectF(0, h - 2 * r, 2 * r, 2 * r), 90, 90)
    path.lineTo(0, y0 + tr)
    path.arcTo(QRectF(0, y0, 2 * tr, 2 * tr), 180, 90)
    path.closeSubpath()
    return path


def _draw_rounded_shadow_layers(
    painter: QPainter,
    w: float,
    h: float,
    r: float,
    *,
    offset_y: float,
    layers: list[tuple[float, int]],
):
    painter.save()
    painter.setPen(Qt.NoPen)
    for spread, alpha in layers:
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(-spread, 0, w + spread * 2, h + spread + offset_y),
            r + spread * 0.3,
            r + spread * 0.3,
        )
        painter.setBrush(QColor(0, 0, 0, alpha))
        painter.drawPath(path)
    painter.restore()


def _draw_rounded_shadow_full(painter: QPainter, w: float, h: float, r: float):
    _draw_rounded_shadow_layers(
        painter,
        w,
        h,
        r,
        offset_y=12,
        layers=[(28, 18), (22, 14), (16, 10), (10, 7), (6, 4), (3, 2)],
    )


def _draw_rounded_shadow_light(painter: QPainter, w: float, h: float, r: float):
    _draw_rounded_shadow_layers(
        painter,
        w,
        h,
        r,
        offset_y=4,
        layers=[(4, 4), (8, 6)],
    )


def paint_dark_gradient(painter: QPainter, panel: QPainterPath):
    bounds = panel.boundingRect()
    grad = QLinearGradient(0, bounds.top(), 0, bounds.bottom())
    grad.setColorAt(0.0, QColor(4, 8, 20))
    grad.setColorAt(0.5, QColor(8, 14, 30))
    grad.setColorAt(1.0, QColor(3, 6, 16))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawPath(panel)


def paint_crystal_glass(
    painter: QPainter,
    w: float,
    h: float,
    *,
    radius: float | None = None,
    compact: bool = False,
    shadow: ShadowProfile = DEFAULT_CRYSTAL_SHADOW,
    fill_alpha: int | None = None,
):
    """Paint shadow, gradient underlay, and crystal glass layers."""
    if w <= 0 or h <= 0:
        return

    if radius is None:
        if compact:
            radius = min(COMPACT_CORNER_RADIUS, h / 2)
        else:
            radius = CORNER_RADIUS

    inset = _inset_panel_path(w, h, radius, 1.0)
    ir = max(0.0, radius - 1.0)
    r, g, b = GLASS_FILL_RGB
    alpha = GLASS_FILL_ALPHA if fill_alpha is None else max(0, min(255, fill_alpha))

    if shadow == "full":
        _draw_rounded_shadow_full(painter, w, h, radius)
    elif shadow == "light":
        _draw_rounded_shadow_light(painter, w, h, radius)

    painter.save()
    painter.setClipPath(inset)

    paint_dark_gradient(painter, inset)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(r, g, b, alpha))
    painter.drawPath(inset)

    painter.setPen(QPen(QColor(255, 255, 255, GLASS_BORDER_ALPHA), 1.0))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(1.0, 1.0, w - 2, h - 2), ir, ir)

    painter.setPen(Qt.NoPen)
    grad1 = QLinearGradient(0, 0, 0, h * 0.45)
    grad1.setColorAt(0.00, QColor(255, 255, 255, 30))
    grad1.setColorAt(0.15, QColor(255, 255, 255, 14))
    grad1.setColorAt(0.40, QColor(255, 255, 255, 3))
    grad1.setColorAt(1.00, QColor(255, 255, 255, 0))
    top_band = QPainterPath()
    top_band.addRect(QRectF(0, 0, w, h * 0.45))
    painter.fillPath(top_band, QBrush(grad1))

    grad2 = QLinearGradient(0, 3, 0, h * 0.18)
    grad2.setColorAt(0.00, QColor(255, 255, 255, 45))
    grad2.setColorAt(0.08, QColor(255, 255, 255, 24))
    grad2.setColorAt(0.30, QColor(255, 255, 255, 4))
    grad2.setColorAt(0.80, QColor(255, 255, 255, 0))
    top_hi = QPainterPath()
    top_hi.addRoundedRect(QRectF(8, 3, w - 16, h * 0.18), min(ir, 8), min(ir, 8))
    painter.fillPath(top_hi, QBrush(grad2))

    if not compact and h >= 120:
        bot_y = h * 0.75
        bot_path = _bottom_glow_path(w, h, radius, 0.75, top_r=14)
        bot_grad = QLinearGradient(0, bot_y, 0, h)
        bot_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        bot_grad.setColorAt(0.6, QColor(255, 255, 255, 3))
        bot_grad.setColorAt(1.0, QColor(255, 255, 255, 10))
        painter.fillPath(bot_path, QBrush(bot_grad))

        for left in (True, False):
            wedge = _corner_wedge_path(w, h, radius, left)
            cx = 12.0 if left else w - 12.0
            corner = QRadialGradient(QPointF(cx, 16), min(180.0, w * 0.25))
            peak = 10 if left else 7
            corner.setColorAt(0.0, QColor(255, 255, 255, peak))
            corner.setColorAt(0.6, QColor(255, 255, 255, 2))
            corner.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillPath(wedge, QBrush(corner))
    elif compact:
        edge = QLinearGradient(0, 0, 0, h)
        edge.setColorAt(0.0, QColor(255, 255, 255, 18))
        edge.setColorAt(0.35, QColor(255, 255, 255, 0))
        painter.fillPath(inset, QBrush(edge))

    painter.restore()
