"""Shared dark crystal glass QPainter background for native shells."""

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


def _panel_path(w: float, h: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), r, r)
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


def _draw_rounded_shadow(painter: QPainter, w: float, h: float, r: float):
    painter.save()
    painter.setPen(Qt.NoPen)
    offset_y = 12
    layers = [
        (28, 18),
        (22, 14),
        (16, 10),
        (10, 7),
        (6, 4),
        (3, 2),
    ]
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


def paint_dark_gradient(painter: QPainter, w: float, h: float, panel: QPainterPath):
    grad = QLinearGradient(0, 0, w, h)
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
):
    """Paint shadow, gradient underlay, and crystal glass layers."""
    if w <= 0 or h <= 0:
        return

    if radius is None:
        if compact:
            radius = min(COMPACT_CORNER_RADIUS, h / 2)
        else:
            radius = CORNER_RADIUS

    panel = _panel_path(w, h, radius)

    _draw_rounded_shadow(painter, w, h, radius)

    painter.save()
    painter.setClipPath(panel)
    paint_dark_gradient(painter, w, h, panel)
    painter.restore()

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(6, 10, 22, 165))
    painter.drawPath(panel)

    painter.save()
    painter.setClipPath(panel)

    painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)

    painter.setPen(Qt.NoPen)
    grad1 = QLinearGradient(0, 0, 0, h * 0.45)
    grad1.setColorAt(0.00, QColor(255, 255, 255, 30))
    grad1.setColorAt(0.15, QColor(255, 255, 255, 14))
    grad1.setColorAt(0.40, QColor(255, 255, 255, 3))
    grad1.setColorAt(1.00, QColor(255, 255, 255, 0))
    painter.setBrush(QBrush(grad1))
    painter.drawRect(QRectF(0, 0, w, h * 0.45))

    grad2 = QLinearGradient(0, 3, 0, h * 0.18)
    grad2.setColorAt(0.00, QColor(255, 255, 255, 45))
    grad2.setColorAt(0.08, QColor(255, 255, 255, 24))
    grad2.setColorAt(0.30, QColor(255, 255, 255, 4))
    grad2.setColorAt(0.80, QColor(255, 255, 255, 0))
    painter.setBrush(QBrush(grad2))
    painter.drawRect(QRectF(8, 3, w - 16, h * 0.18))

    if not compact and h >= 80:
        bot_y = h * 0.75
        bot_path = _bottom_glow_path(w, h, radius, 0.75, top_r=14)
        bot_grad = QLinearGradient(0, bot_y, 0, h)
        bot_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        bot_grad.setColorAt(0.6, QColor(255, 255, 255, 3))
        bot_grad.setColorAt(1.0, QColor(255, 255, 255, 10))
        painter.setBrush(QBrush(bot_grad))
        painter.drawPath(bot_path)

        corner = QRadialGradient(QPointF(12, 16), 180)
        corner.setColorAt(0.0, QColor(255, 255, 255, 10))
        corner.setColorAt(0.6, QColor(255, 255, 255, 2))
        corner.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(corner))
        painter.drawRect(QRectF(0, 0, w * 0.3, h * 0.3))

        corner2 = QRadialGradient(QPointF(w - 12, 16), 180)
        corner2.setColorAt(0.0, QColor(255, 255, 255, 7))
        corner2.setColorAt(0.6, QColor(255, 255, 255, 1))
        corner2.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(corner2))
        painter.drawRect(QRectF(w * 0.7, 0, w * 0.3, h * 0.3))
    elif compact:
        edge = QLinearGradient(0, 0, 0, h)
        edge.setColorAt(0.0, QColor(255, 255, 255, 18))
        edge.setColorAt(0.35, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(edge))
        painter.drawRect(QRectF(0, 0, w, h))

    painter.restore()
