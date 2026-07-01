"""Nav SVG icons — paths from ui/web/index.html viewMedium nav."""
from PyQt5.QtCore import QByteArray, QSize, Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter
from PyQt5.QtSvg import QSvgRenderer

from ui.native.design_tokens import ACCENT, TEXT_SECONDARY, TEXT_TERTIARY

_NAV_SVGS = {
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
    "mic": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<path d="M12 1a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" fill="none" stroke="{color}" stroke-width="1.5"/>'
        '<path d="M19 10v1a7 7 0 0 1-14 0v-1" fill="none" stroke="{color}" stroke-width="1.5"/>'
        '<line x1="12" y1="19" x2="12" y2="23" stroke="{color}" stroke-width="1.5"/>'
        '<line x1="8" y1="23" x2="16" y2="23" stroke="{color}" stroke-width="1.5"/>'
        "</svg>"
    ),
    "send": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<path d="M5 12h14" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        '<path d="M12 5l7 7-7 7" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
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


def svg_icon(key: str, size: int = 18, color: str = TEXT_SECONDARY) -> QIcon:
    tpl = _NAV_SVGS.get(key, _NAV_SVGS["guide"])
    svg = tpl.format(color=color).encode("utf-8")
    renderer = QSvgRenderer(QByteArray(svg))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def nav_icon(key: str, active: bool = False) -> QIcon:
    return svg_icon(key, color=ACCENT if active else TEXT_SECONDARY)


def action_icon(key: str, color: str = TEXT_TERTIARY) -> QIcon:
    return svg_icon(key, size=16, color=color)
