"""Apply global UI font — Chinese-friendly stack at 13px."""
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from ui.native.layout_tokens import (
    FONT_FAMILY,
    FONT_FAMILY_FALLBACK,
    FONT_SIZE_BASE,
)


def apply_app_font(app: QApplication, size: int | None = None) -> None:
    pt = FONT_SIZE_BASE if size is None else size
    font = QFont(FONT_FAMILY, pt)
    font.setFamilies([FONT_FAMILY, FONT_FAMILY_FALLBACK, "PingFang SC", "sans-serif"])
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)
