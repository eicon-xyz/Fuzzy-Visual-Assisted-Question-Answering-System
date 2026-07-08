"""Luxury script title — liquid-gold HAJIMI with 7 signature fonts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PyQt5.QtCore import Qt, QSize, QPointF, QRect
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
)
from PyQt5.QtWidgets import QSizePolicy, QWidget

GoldMode = Literal["horizontal", "diagonal", "dual_layer"]

_TITLE = "HAJIMI"
_PAD_X = 6
_PAD_Y = 3

_GOLD_DARK = "#B8860B"
_GOLD_MID = "#F5E6A8"
_GOLD_LIGHT = "#C9A84C"
_GOLD_SHADOW = "#8B6914"

DEFAULT_SCRIPT_FONT_ID = "mrs_delafield"

LUXURY_SCRIPT_FONT_IDS = (
    "great_vibes",
    "pinyon",
    "mrs_delafield",
    "sacramento",
    "allura",
    "parisienne",
    "alex_brush",
)

GOLD_MODE_IDS = ("horizontal", "diagonal", "dual_layer")


@dataclass(frozen=True)
class FontPreset:
    label: str
    filename: str
    size: int
    letter_spacing: float = 0.0


LUXURY_SCRIPT_FONTS: dict[str, FontPreset] = {
    "great_vibes": FontPreset("Great Vibes · 飘逸连笔", "GreatVibes-Regular.ttf", 19),
    "pinyon": FontPreset("Pinyon Script · 细线 Copperplate", "PinyonScript-Regular.ttf", 15, 0.8),
    "mrs_delafield": FontPreset("Mrs Saint Delafield · 极细签名", "MrsSaintDelafield-Regular.ttf", 22),
    "sacramento": FontPreset("Sacramento · 横向细签名", "Sacramento-Regular.ttf", 20, 0.5),
    "allura": FontPreset("Allura · 流畅 Script", "Allura-Regular.ttf", 18),
    "parisienne": FontPreset("Parisienne · 法式优雅", "Parisienne-Regular.ttf", 17),
    "alex_brush": FontPreset("Alex Brush · 毛笔签名", "AlexBrush-Regular.ttf", 18),
}

_fonts_loaded = False
_font_families: dict[str, str] = {}


def script_font_labels() -> dict[str, str]:
    return {fid: preset.label for fid, preset in LUXURY_SCRIPT_FONTS.items()}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def ensure_luxury_fonts() -> None:
    global _fonts_loaded
    if _fonts_loaded:
        return
    fonts_dir = _project_root() / "assets" / "fonts"
    for font_id, preset in LUXURY_SCRIPT_FONTS.items():
        path = fonts_dir / preset.filename
        if not path.is_file():
            continue
        fid = QFontDatabase.addApplicationFont(str(path))
        if fid < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(fid)
        if families:
            _font_families[font_id] = families[0]
    _fonts_loaded = True


def _resolve_font_family(font_id: str) -> str:
    ensure_luxury_fonts()
    if font_id in _font_families:
        return _font_families[font_id]
    preset = LUXURY_SCRIPT_FONTS.get(font_id, LUXURY_SCRIPT_FONTS[DEFAULT_SCRIPT_FONT_ID])
    return preset.label.split(" · ", 1)[0]


class LuxuryScriptTitleWidget(QWidget):
    """Top-bar HAJIMI in script with liquid-gold fill."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("LuxuryScriptTitle")
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._gold_mode: GoldMode = "dual_layer"
        self._font_id = DEFAULT_SCRIPT_FONT_ID
        ensure_luxury_fonts()
        self._apply_fixed_size()

    def _preset(self) -> FontPreset:
        return LUXURY_SCRIPT_FONTS.get(self._font_id, LUXURY_SCRIPT_FONTS[DEFAULT_SCRIPT_FONT_ID])

    def _title_font(self) -> QFont:
        preset = self._preset()
        family = _resolve_font_family(self._font_id)
        font = QFont(family, preset.size)
        font.setLetterSpacing(QFont.AbsoluteSpacing, preset.letter_spacing)
        font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        return font

    def set_gold_mode(self, mode: str) -> None:
        if mode in GOLD_MODE_IDS:
            self._gold_mode = mode  # type: ignore[assignment]
            self.update()

    def set_font_id(self, font_id: str) -> None:
        if font_id not in LUXURY_SCRIPT_FONTS:
            return
        self._font_id = font_id
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
