"""Luxury v2 painting — starfield, frosted/kraft bg, shell modes."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen

BgMode = Literal["frosted", "kraft"]
ShellMode = Literal["SA", "SB", "SC"]

STAR_SEED = 42
STAR_COUNT = 200
SB_STAR_STRIP_H = 80.0
STAR_FADE_END_RATIO = 0.75


@dataclass(frozen=True)
class LuxuryV2Tokens:
    bg_primary: str = "#0A0908"
    bg_kraft: str = "#1A1612"
    bg_elevated: str = "#141210"
    secondary: str = "#EBE4D8"
    secondary_muted: str = "#8A8278"
    surface_line: str = "#2A2620"
    gold: str = "#C9A84C"
    shell_glass: tuple[int, int, int, int] = (20, 18, 16, 184)


TOKENS = LuxuryV2Tokens()

_star_cache: dict[tuple[int, int], list[tuple[float, float, int, float]]] = {}


def _parse_hex(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _star_fade(y: float, h: float, *, fade_end_ratio: float = STAR_FADE_END_RATIO) -> float:
    zone = max(1.0, h * fade_end_ratio)
    if y >= zone:
        return 0.0
    t = y / zone
    return max(0.0, (1.0 - t) ** 1.8)


def _star_positions(w: int, h: int) -> list[tuple[float, float, int, float]]:
    key = (w, h)
    if key not in _star_cache:
        rng = random.Random(STAR_SEED)
        zone_h = h * STAR_FADE_END_RATIO
        stars: list[tuple[float, float, int, float]] = []
        for _ in range(STAR_COUNT):
            x = rng.random() * w
            y = (rng.random() ** 1.75) * zone_h
            size = 2 if rng.random() > 0.9 else 1
            opacity = 0.12 + rng.random() * 0.48
            stars.append((x, y, size, opacity))
        _star_cache[key] = stars
    return _star_cache[key]


def _paint_noise(painter: QPainter, rect: QRectF, seed: int, alpha: int, warm: bool) -> None:
    rng = random.Random(seed)
    w, h = int(rect.width()), int(rect.height())
    step = 3
    painter.save()
    painter.setPen(Qt.NoPen)
    for y in range(0, h, step):
        for x in range(0, w, step):
            if rng.random() > 0.35:
                continue
            if warm:
                c = QColor(196, 181, 160, alpha)
            else:
                c = QColor(255, 255, 255, alpha)
            painter.setBrush(c)
            painter.drawRect(x, y, 1, 1)
    painter.restore()


def paint_luxury_background(painter: QPainter, rect: QRectF, mode: BgMode) -> None:
    painter.save()
    painter.setPen(Qt.NoPen)
    if mode == "kraft":
        br, bg, bb = _parse_hex(TOKENS.bg_kraft)
        painter.setBrush(QColor(br, bg, bb))
        painter.drawRect(rect)
        _paint_noise(painter, rect, seed=7, alpha=28, warm=True)
    else:
        br, bg, bb = _parse_hex(TOKENS.bg_primary)
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, QColor(br, bg, bb))
        tr, tg, tb = _parse_hex("#12100E")
        grad.setColorAt(0.55, QColor(tr, tg, tb))
        grad.setColorAt(1.0, QColor(br, bg, bb))
        painter.setBrush(QBrush(grad))
        painter.drawRect(rect)
        _paint_noise(painter, rect, seed=3, alpha=10, warm=False)
    painter.restore()


def paint_luxury_starfield(
    painter: QPainter,
    rect: QRectF,
    intensity: int,
    *,
    bg_mode: BgMode = "frosted",
) -> None:
    if intensity <= 0 or bg_mode == "kraft":
        return
    w, h = max(1, int(rect.width())), max(1, int(rect.height()))
    scale = max(0.0, min(1.0, intensity / 100.0))
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    for x, y, size, opacity in _star_positions(w, h):
        fade = _star_fade(y, float(h))
        if fade <= 0.0:
            continue
        alpha = int(opacity * scale * fade * 255)
        if alpha < 4:
            continue
        bright = min(255, int(alpha * 1.2)) if size >= 2 else alpha
        cx = rect.x() + x
        cy = rect.y() + y
        glow = int(bright * 0.22)
        if glow >= 4:
            painter.setBrush(QColor(255, 248, 235, glow))
            painter.drawEllipse(QPointF(cx, cy), size * 1.1, size * 1.1)
        painter.setBrush(QColor(255, 255, 255, bright))
        painter.drawEllipse(QPointF(cx, cy), size * 0.55, size * 0.55)
    painter.restore()


def _rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_luxury_shell(
    painter: QPainter,
    rect: QRectF,
    shell_mode: ShellMode,
    radius: float,
    *,
    compact: bool = False,
) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = _rounded_path(rect, radius)
    line = QColor(TOKENS.surface_line)

    if shell_mode == "SA":
        sr, sg, sb, sa = TOKENS.shell_glass
        painter.fillPath(path, QColor(sr, sg, sb, sa))
        pen = QPen(QColor(255, 248, 240, 28))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    elif shell_mode == "SB":
        strip = min(SB_STAR_STRIP_H, rect.height() * 0.14) if not compact else min(18.0, rect.height() * 0.35)
        body = QRectF(rect.x(), rect.y() + strip, rect.width(), rect.height() - strip)
        body_path = _rounded_path(body, radius)
        er, eg, eb = _parse_hex(TOKENS.bg_elevated)
        painter.fillPath(body_path, QColor(er, eg, eb))
        pen = QPen(line)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(body_path)
        sep_y = rect.y() + strip
        painter.drawLine(
            QPointF(rect.x() + 8, sep_y),
            QPointF(rect.right() - 8, sep_y),
        )
    else:
        pen = QPen(line)
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        bar_y = rect.y() + (36.0 if not compact else 14.0)
        painter.drawLine(
            QPointF(rect.x() + 8, bar_y),
            QPointF(rect.right() - 8, bar_y),
        )
    painter.restore()


def paint_luxury_frame(
    painter: QPainter,
    rect: QRectF,
    *,
    bg_mode: BgMode = "frosted",
    shell_mode: ShellMode = "SA",
    star_intensity: int = 0,
    radius: float = 10.0,
    compact: bool = False,
) -> None:
    """Full luxury shell stack: background → stars → shell overlay."""
    paint_luxury_background(painter, rect, bg_mode)
    paint_luxury_starfield(painter, rect, star_intensity, bg_mode=bg_mode)
    paint_luxury_shell(painter, rect, shell_mode, radius, compact=compact)
