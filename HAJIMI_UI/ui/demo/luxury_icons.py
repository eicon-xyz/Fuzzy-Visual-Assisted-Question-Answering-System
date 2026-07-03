"""Demo-only luxury line icons — white stroke + gold top-left glow."""
from __future__ import annotations

from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtGui import QIcon, QPainter, QPen, QColor, QPixmap
from PyQt5.QtSvg import QSvgRenderer

_GOLD = QColor(201, 168, 76, 90)
_STROKE = "#EBE4D8"

_SVGS: dict[str, str] = {
    "menu": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<line x1="4" y1="7" x2="20" y2="7" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="4" y1="12" x2="20" y2="12" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="4" y1="17" x2="20" y2="17" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        "</svg>"
    ),
    "mic": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<rect x="9" y="3" width="6" height="11" rx="3" fill="none" stroke="{color}" stroke-width="1.5"/>'
        '<path d="M6 11a6 6 0 0 0 12 0" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="12" y1="17" x2="12" y2="20" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        "</svg>"
    ),
    "send": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<path d="M5 12h12M13 7l5 5-5 5" fill="none" stroke="{color}" stroke-width="1.5" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
    "guide": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<circle cx="12" cy="12" r="8" fill="none" stroke="{color}" stroke-width="1.5"/>'
        '<circle cx="12" cy="12" r="2.5" fill="{color}"/>'
        "</svg>"
    ),
}


def _render_svg(svg: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pm


def luxury_icon(name: str, size: int = 18) -> QIcon:
    template = _SVGS.get(name)
    if not template:
        return QIcon()
    gold_svg = template.format(color="#C9A84C")
    white_svg = template.format(color=_STROKE)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    gold_pm = _render_svg(gold_svg, size)
    painter.drawPixmap(-1, -1, gold_pm)
    white_pm = _render_svg(white_svg, size)
    painter.drawPixmap(0, 0, white_pm)
    painter.end()
    return QIcon(pm)
