"""Luxury line icons — white stroke + gold top-left glow (721 style)."""
from __future__ import annotations

from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QPushButton

try:
    from PyQt5.QtSvg import QSvgRenderer

    _HAS_SVG = True
except ImportError:
    QSvgRenderer = None  # type: ignore[misc, assignment]
    _HAS_SVG = False

_STROKE = "#EBE4D8"
_GOLD = "#C9A84C"
_GOLD_ACTIVE = "#E8C96A"

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
        '<circle cx="12" cy="12" r="9" fill="none" stroke="{color}" stroke-width="2"/>'
        '<circle cx="12" cy="12" r="3" fill="{color}"/>'
        "</svg>"
    ),
    "steps": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<line x1="8" y1="6" x2="21" y2="6" stroke="{color}" stroke-width="2"/>'
        '<line x1="8" y1="12" x2="21" y2="12" stroke="{color}" stroke-width="2"/>'
        '<line x1="8" y1="18" x2="21" y2="18" stroke="{color}" stroke-width="2"/>'
        "</svg>"
    ),
    "blueprint": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<path d="M3 6l9-4 9 4v12l-9 4-9-4V6z" fill="none" stroke="{color}" stroke-width="2"/>'
        "</svg>"
    ),
    "notifications": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<path d="M18 8a6 6 0 0 0-12 0c0 6-3 7-3 7h18s-3-1-3-7" '
        'fill="none" stroke="{color}" stroke-width="2"/>'
        "</svg>"
    ),
    "settings": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<circle cx="12" cy="12" r="3" fill="none" stroke="{color}" stroke-width="2"/>'
        '<path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2" '
        'stroke="{color}" stroke-width="2"/>'
        "</svg>"
    ),
    "logo": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<path d="M12 2L14 8L20 10L14 12L12 18L10 12L4 10L10 8L12 2Z" fill="{color}"/>'
        "</svg>"
    ),
    "compact": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<rect x="3" y="8" width="18" height="8" rx="2" fill="none" stroke="{color}" stroke-width="1.5"/>'
        '<path d="M8 12h8" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        "</svg>"
    ),
    "logout": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" fill="none" stroke="{color}" stroke-width="1.5"/>'
        '<path d="M16 17l5-5-5-5" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="21" y1="12" x2="9" y2="12" stroke="{color}" stroke-width="1.5"/>'
        "</svg>"
    ),
}


def _render_svg(svg: str, size: int) -> QPixmap:
    if not _HAS_SVG:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        return pm
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pm


def _compose_721_icon(name: str, size: int, *, active: bool = False) -> QIcon:
    template = _SVGS.get(name)
    if not template:
        return QIcon()
    gold_color = _GOLD_ACTIVE if active else _GOLD
    stroke = gold_color if active else _STROKE
    gold_svg = template.format(color=gold_color)
    white_svg = template.format(color=stroke if active else _STROKE)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    if not active:
        gold_pm = _render_svg(gold_svg, size)
        painter.drawPixmap(-1, -1, gold_pm)
    white_pm = _render_svg(white_svg, size)
    painter.drawPixmap(0, 0, white_pm)
    painter.end()
    return QIcon(pm)


def luxury_icon(name: str, size: int = 18, *, active: bool = False) -> QIcon:
    return _compose_721_icon(name, size, active=active)


def luxury_nav_icon(key: str, active: bool = False, *, size: int = 18) -> QIcon:
    return _compose_721_icon(key, size, active=active)


def apply_luxury_menu_icon(button: QPushButton, *, size: int = 18) -> None:
    button.setIcon(luxury_icon("menu", size))
    button.setText("")
