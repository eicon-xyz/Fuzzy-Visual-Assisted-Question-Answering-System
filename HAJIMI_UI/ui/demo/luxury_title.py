"""Luxury v2 demo title — liquid-gold script HAJIMI (Demo only)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from PyQt5.QtCore import Qt, QSize, QPointF, QRect
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontInfo,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
)
from PyQt5.QtWidgets import QSizePolicy, QWidget

GoldMode = Literal["horizontal", "diagonal", "dual_layer"]
FontTier = Literal["google", "advanced"]

_TITLE = "HAJIMI"
_PAD_X = 6
_PAD_Y = 3

_GOLD_DARK = "#B8860B"
_GOLD_MID = "#F5E6A8"
_GOLD_LIGHT = "#C9A84C"
_GOLD_SHADOW = "#8B6914"

_fonts_loaded = False
_font_family_google = ""
_font_family_advanced = ""


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_luxury_fonts() -> None:
    global _fonts_loaded, _font_family_google, _font_family_advanced
    if _fonts_loaded:
        return
    fonts_dir = _project_root() / "assets" / "fonts"
    mapping = (
        ("GreatVibes-Regular.ttf", "google"),
        ("PinyonScript-Regular.ttf", "advanced"),
    )
    for filename, tier in mapping:
        path = fonts_dir / filename
        if not path.is_file():
            continue
        fid = QFontDatabase.addApplicationFont(str(path))
        if fid < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(fid)
        if not families:
            continue
        if tier == "google":
            _font_family_google = families[0]
        else:
            _font_family_advanced = families[0]
    _fonts_loaded = True


def _resolve_font_family(tier: FontTier) -> str:
    ensure_luxury_fonts()
    if tier == "advanced" and _font_family_advanced:
        return _font_family_advanced
    if _font_family_google:
        return _font_family_google
    for name in ("Great Vibes", "Pinyon Script", "Segoe Script", "Edwardian Script ITC"):
        font = QFont(name)
        if font.exactMatch() or QFontInfo(font).family() == name:
            return name
    return "Segoe UI"


class LuxuryScriptTitleWidget(QWidget):
    """Top-bar HAJIMI in thin script with liquid-gold fill."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("LuxuryScriptTitle")
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._gold_mode: GoldMode = "horizontal"
        self._font_tier: FontTier = "google"
        ensure_luxury_fonts()
        self._apply_fixed_size()

    def _title_font(self) -> QFont:
        family = _resolve_font_family(self._font_tier)
        if self._font_tier == "advanced":
            font = QFont(family, 15)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        else:
            font = QFont(family, 19)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 0.0)
        font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        if family in ("Segoe UI",):
            font.setItalic(True)
        return font

    def set_gold_mode(self, mode: str) -> None:
        if mode in ("horizontal", "diagonal", "dual_layer"):
            self._gold_mode = mode  # type: ignore[assignment]
            self.update()

    def set_font_tier(self, tier: str) -> None:
        if tier in ("google", "advanced"):
            self._font_tier = tier  # type: ignore[assignment]
            self._apply_fixed_size()
            self.updateGeometry()
            self.update()

    def _text_bounds(self) -> tuple[QRect, QFontMetrics]:
        metrics = QFontMetrics(self._title_font())
        rect = metrics.boundingRect(_TITLE)
        return rect, metrics

    def _content_size(self) -> QSize:
        rect, _ = self._text_bounds()
        w = rect.width() + _PAD_X * 2
        h = rect.height() + _PAD_Y * 2
        return QSize(max(w, 64), max(h, 22))

    def _baseline_y(self, metrics: QFontMetrics) -> int:
        rect, _ = self._text_bounds()
        return _PAD_Y - rect.top()

    def _apply_fixed_size(self) -> None:
        size = self.sizeHint()
        self.setMinimumSize(size)
        self.setFixedSize(size)

    def sizeHint(self) -> QSize:
        return self._content_size()

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, event):
        self._apply_fixed_size()
        super().resizeEvent(event)

    def _draw_gold_text(
        self, painter: QPainter, x: float, y: float, pen: QPen, *, offset_y: float = 0.0
    ) -> None:
        painter.setPen(pen)
        painter.drawText(QPointF(x, y + offset_y), _TITLE)

    def paintEvent(self, event):
        if self.width() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        font = self._title_font()
        painter.setFont(font)
        rect, metrics = self._text_bounds()
        x = float(_PAD_X)
        y = float(self._baseline_y(metrics))
        width = float(rect.width())
        if self._gold_mode == "dual_layer":
            self._paint_dual_layer(painter, x, y, width)
        else:
            grad = self._build_gradient(int(x), int(y), int(width))
            self._draw_gold_text(painter, x, y, QPen(QBrush(grad), 0.5))
        painter.end()

    def _build_gradient(self, x: int, y: int, width: int) -> QLinearGradient:
        if self._gold_mode == "diagonal":
            grad = QLinearGradient(x, y - 4, x + width, y + 14)
        else:
            grad = QLinearGradient(x, 0, x + width, 0)
        grad.setColorAt(0.0, QColor(_GOLD_DARK))
        grad.setColorAt(0.45, QColor(_GOLD_MID))
        grad.setColorAt(1.0, QColor(_GOLD_LIGHT))
        return grad

    def _paint_dual_layer(self, painter: QPainter, x: float, y: float, width: float) -> None:
        painter.setFont(self._title_font())
        shadow = QPen(QColor(_GOLD_SHADOW), 0.6)
        self._draw_gold_text(painter, x, y, shadow, offset_y=0.5)
        grad = QLinearGradient(x, y - 2, x + width * 0.55, y + 4)
        grad.setColorAt(0.0, QColor(_GOLD_MID))
        grad.setColorAt(1.0, QColor(_GOLD_LIGHT))
        self._draw_gold_text(painter, x, y, QPen(QBrush(grad), 0.4))
