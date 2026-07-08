"""Top bar art title widget — gradient / logo / display font (no background pill)."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
)
from PyQt5.QtWidgets import QSizePolicy, QWidget

from ui.native.nav_icons import svg_icon
from ui.native.visual_tokens import ACCENT

TITLE_ART_MODES: dict[str, str] = {
    "gradient": "A · 渐变艺术字",
    "logo_gradient": "B · Logo + 渐变",
    "display_font": "C · 展示字体",
}

TITLE_ART_MODE_IDS = tuple(TITLE_ART_MODES.keys())
DEFAULT_TITLE_ART = "gradient"


class TitleArtWidget(QWidget):
    """Top-bar title line: gradient / logo / display-font (HAJIMI only)."""

    _TITLE = "HAJIMI"
    _LINE_HEIGHT = 20

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TitleArt")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._mode = DEFAULT_TITLE_ART
        self._accent = ACCENT
        self._apply_fixed_size()

    def _title_font(self) -> QFont:
        if self._mode == "display_font":
            font = QFont("Segoe UI Variable Display", 13)
            if not font.exactMatch():
                font = QFont("Segoe UI", 13)
            font.setWeight(QFont.Bold)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
            return font
        font = QFont("Segoe UI", 13)
        font.setWeight(QFont.Bold)
        return font

    def _text_origin(self) -> tuple[int, int]:
        if self._mode == "logo_gradient":
            return 20, 15
        return 0, 15

    def _content_width(self) -> int:
        metrics = QFontMetrics(self._title_font())
        width = metrics.horizontalAdvance(self._TITLE)
        if self._mode == "logo_gradient":
            width += 20
        return max(width, 48)

    def _content_height(self) -> int:
        return self._LINE_HEIGHT

    def _apply_fixed_size(self) -> None:
        size = self.sizeHint()
        self.setFixedSize(size)
        self.setMaximumWidth(size.width())

    def set_mode(self, mode: str) -> None:
        if mode in TITLE_ART_MODE_IDS:
            self._mode = mode
            self._apply_fixed_size()
            self.updateGeometry()
            self.update()

    def set_accent(self, hex_color: str) -> None:
        self._accent = hex_color
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._content_width(), self._content_height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, event):
        self._apply_fixed_size()
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self.width() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._mode == "logo_gradient":
            self._paint_logo_gradient(painter)
        elif self._mode == "display_font":
            self._paint_display_font(painter)
        else:
            self._paint_gradient(painter)
        painter.end()

    def _draw_gradient_text(
        self, painter: QPainter, x: int, y: int, title: str | None = None
    ) -> None:
        title = title or self._TITLE
        font = self._title_font()
        painter.setFont(font)
        metrics = QFontMetrics(font)
        grad = QLinearGradient(x, 0, x + metrics.horizontalAdvance(title), 0)
        grad.setColorAt(0.0, QColor(self._accent))
        grad.setColorAt(1.0, QColor("#f1f5f9"))
        painter.setPen(QPen(QBrush(grad), 1))
        painter.drawText(x, y, title)

    def _paint_gradient(self, painter: QPainter) -> None:
        tx, ty = self._text_origin()
        self._draw_gradient_text(painter, tx, ty)

    def _paint_logo_gradient(self, painter: QPainter) -> None:
        logo = svg_icon("logo", size=16, color=self._accent)
        painter.drawPixmap(0, 2, logo.pixmap(16, 16))
        tx, ty = self._text_origin()
        self._draw_gradient_text(painter, tx, ty)

    def _paint_display_font(self, painter: QPainter) -> None:
        font = self._title_font()
        painter.setFont(font)
        tx, ty = self._text_origin()
        painter.setPen(QColor("#f1f5f9"))
        painter.drawText(tx, ty, self._TITLE)
