"""Shared shell background painting — QSS body/highlights and Crystal top light."""
from __future__ import annotations

from typing import Literal

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

from ui.native import crystal_glass as cg

LightMode = Literal["pro_only", "dual", "crystal_only"]
QssHighlightMode = Literal["pro_only", "band_only", "dual_lite"]
QssBodyMode = Literal["solid", "vertical_grad"]

LIGHT_MODES: dict[str, str] = {
    "pro_only": "A · pro 对角顶光",
    "dual": "B · crystal + pro 双层",
    "crystal_only": "C · crystal 顶光",
}

QSS_HIGHLIGHT_MODES: dict[str, str] = {
    "pro_only": "A · pro 对角",
    "band_only": "B · 顶缘 band",
    "dual_lite": "C · band + pro 双层",
}

QSS_BODY_MODES: dict[str, str] = {
    "solid": "A · 纯实底",
    "vertical_grad": "B · 竖渐变",
}

LIGHT_MODE_IDS = tuple(LIGHT_MODES.keys())
QSS_HIGHLIGHT_MODE_IDS = tuple(QSS_HIGHLIGHT_MODES.keys())
QSS_BODY_MODE_IDS = tuple(QSS_BODY_MODES.keys())

DEFAULT_LIGHT_MODE: LightMode = "dual"
DEFAULT_TOP_LIGHT_PEAK = 34
DEFAULT_QSS_HIGHLIGHT: QssHighlightMode = "dual_lite"
DEFAULT_QSS_BODY: QssBodyMode = "solid"
DEFAULT_QSS_HIGHLIGHT_PEAK = 34
DEFAULT_SHELL_LUMINANCE = 100

PEAK_MAX = 60


def _scale_luminance_rgb(r: int, g: int, b: int, luminance: int) -> tuple[int, int, int]:
    t = luminance / 100.0
    if t <= 1.0:
        return (int(r * t), int(g * t), int(b * t))

    def lift(c: int) -> int:
        return min(255, int(c + (255 - c) * (t - 1.0) * 0.25))

    return (lift(r), lift(g), lift(b))


def _paint_dark_gradient(
    painter: QPainter,
    panel: QPainterPath,
    luminance: int = DEFAULT_SHELL_LUMINANCE,
    gradient_tint: tuple[int, int, int] | None = None,
) -> None:
    bounds = panel.boundingRect()
    grad = QLinearGradient(0, bounds.top(), 0, bounds.bottom())
    if gradient_tint is None:
        stops = ((0.0, (4, 8, 20)), (0.5, (8, 14, 30)), (1.0, (3, 6, 16)))
    else:
        tr, tg, tb = gradient_tint
        stops = (
            (0.0, (max(0, tr - 2), max(0, tg - 2), max(0, tb - 2))),
            (0.5, (tr, tg, tb)),
            (1.0, (max(0, tr - 3), max(0, tg - 4), max(0, tb - 6))),
        )
    for pos, rgb in stops:
        r, g, b = _scale_luminance_rgb(*rgb, luminance)
        grad.setColorAt(pos, QColor(r, g, b))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawPath(panel)


def _draw_pro_top_light(painter: QPainter, w: float, h: float, peak: int) -> None:
    peak = max(0, min(PEAK_MAX, peak))
    if peak <= 0:
        return
    high_grad = QLinearGradient(0, 0, w, h * 0.6)
    high_grad.setColorAt(0.0, QColor(255, 255, 255, peak))
    high_grad.setColorAt(0.15, QColor(255, 255, 255, max(0, int(peak * 0.33))))
    high_grad.setColorAt(0.4, QColor(255, 255, 255, 0))
    high_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(high_grad))
    painter.drawRect(QRectF(0, 0, w, h))


def _draw_crystal_top_highlights(
    painter: QPainter,
    w: float,
    h: float,
    ir: float,
    peak_mult: float,
) -> None:
    m = max(0.0, peak_mult)

    grad1 = QLinearGradient(0, 0, 0, h * 0.45)
    grad1.setColorAt(0.00, QColor(255, 255, 255, int(30 * m)))
    grad1.setColorAt(0.15, QColor(255, 255, 255, int(14 * m)))
    grad1.setColorAt(0.40, QColor(255, 255, 255, int(3 * m)))
    grad1.setColorAt(1.00, QColor(255, 255, 255, 0))
    top_band = QPainterPath()
    top_band.addRect(QRectF(0, 0, w, h * 0.45))
    painter.fillPath(top_band, QBrush(grad1))

    grad2 = QLinearGradient(0, 3, 0, h * 0.18)
    grad2.setColorAt(0.00, QColor(255, 255, 255, int(45 * m)))
    grad2.setColorAt(0.08, QColor(255, 255, 255, int(24 * m)))
    grad2.setColorAt(0.30, QColor(255, 255, 255, int(4 * m)))
    grad2.setColorAt(0.80, QColor(255, 255, 255, 0))
    top_hi = QPainterPath()
    top_hi.addRoundedRect(QRectF(8, 3, w - 16, h * 0.18), min(ir, 8), min(ir, 8))
    painter.fillPath(top_hi, QBrush(grad2))


def paint_crystal_shell(
    painter: QPainter,
    w: float,
    h: float,
    *,
    radius: float | None = None,
    compact: bool = False,
    fill_rgb: tuple[int, int, int] | None = None,
    fill_alpha: int | None = None,
    light_mode: LightMode = DEFAULT_LIGHT_MODE,
    top_light_peak: int = DEFAULT_TOP_LIGHT_PEAK,
    shell_luminance: int = DEFAULT_SHELL_LUMINANCE,
    gradient_tint: tuple[int, int, int] | None = None,
) -> None:
    """Crystal shell paint; outer shadow via DropShadow, not painter layers."""
    if w <= 0 or h <= 0:
        return

    light_mode = str(light_mode)  # type: ignore[assignment]

    if radius is None:
        radius = min(cg.COMPACT_CORNER_RADIUS, h / 2) if compact else cg.CORNER_RADIUS

    inset = cg._inset_panel_path(w, h, radius, 1.0)
    ir = max(0.0, radius - 1.0)
    r, g, b = fill_rgb if fill_rgb is not None else cg.GLASS_FILL_RGB
    base_alpha = cg.GLASS_FILL_ALPHA if fill_alpha is None else max(0, min(255, fill_alpha))
    alpha = max(0, min(255, int(base_alpha * shell_luminance / 100)))

    painter.save()
    painter.setClipPath(inset)

    _paint_dark_gradient(painter, inset, shell_luminance, gradient_tint)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(r, g, b, alpha))
    painter.drawPath(inset)

    painter.setPen(QPen(QColor(255, 255, 255, cg.GLASS_BORDER_ALPHA), 1.0))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(1.0, 1.0, w - 2, h - 2), ir, ir)

    peak_mult = top_light_peak / 45.0 if top_light_peak else 0.0

    if light_mode in ("crystal_only", "dual"):
        _draw_crystal_top_highlights(
            painter, w, h, ir, peak_mult if light_mode == "crystal_only" else 1.0
        )

    if light_mode in ("pro_only", "dual"):
        _draw_pro_top_light(painter, w, h, top_light_peak)

    if not compact and h >= 120:
        bot_y = h * 0.75
        bot_path = cg._bottom_glow_path(w, h, radius, 0.75, top_r=14)
        bot_grad = QLinearGradient(0, bot_y, 0, h)
        bot_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        bot_grad.setColorAt(0.6, QColor(255, 255, 255, 3))
        bot_grad.setColorAt(1.0, QColor(255, 255, 255, 10))
        painter.fillPath(bot_path, QBrush(bot_grad))

        for left in (True, False):
            wedge = cg._corner_wedge_path(w, h, radius, left)
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


def paint_qss_shell(
    painter: QPainter,
    w: float,
    h: float,
    *,
    rgba: tuple[int, int, int, int],
    body_mode: QssBodyMode = DEFAULT_QSS_BODY,
    highlight_mode: QssHighlightMode = DEFAULT_QSS_HIGHLIGHT,
    highlight_peak: int = DEFAULT_QSS_HIGHLIGHT_PEAK,
    radius: float,
    compact: bool = False,
) -> None:
    """QSS solid fill + optional page glass highlights."""
    if w <= 0 or h <= 0:
        return

    body_mode = str(body_mode)  # type: ignore[assignment]
    highlight_mode = str(highlight_mode)  # type: ignore[assignment]
    r, g, b, a = rgba
    shell_path = QPainterPath()
    shell_path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    ir = max(0.0, radius - 1.0)

    painter.save()
    painter.setClipPath(shell_path)

    if body_mode == "vertical_grad":
        grad = QLinearGradient(0, 0, 0, h)
        top_a = min(255, int(a * 1.06))
        bot_a = max(0, int(a * 0.94))
        grad.setColorAt(0.0, QColor(r, g, b, top_a))
        grad.setColorAt(1.0, QColor(r, g, b, bot_a))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(shell_path)
    else:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(r, g, b, a))
        painter.drawPath(shell_path)

    if highlight_mode in ("band_only", "dual_lite"):
        _draw_crystal_top_highlights(painter, w, h, ir, 1.0)

    if highlight_mode in ("pro_only", "dual_lite"):
        _draw_pro_top_light(painter, w, h, highlight_peak)

    painter.restore()

    painter.setPen(QPen(QColor(255, 255, 255, 30), 1.0))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), ir, ir)
