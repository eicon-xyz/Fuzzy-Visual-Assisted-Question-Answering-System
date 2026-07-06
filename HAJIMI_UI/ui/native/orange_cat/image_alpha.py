"""Load PNG/JPG with corner white/cream knock-out."""
from __future__ import annotations

from collections import deque
from typing import Literal

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPixmap

KNOCKOUT_MAX_SIDE = 256

KnockOutMode = Literal["auto", "always", "never"]


def _is_knockout_background(color: QColor, *, tolerance: int = 22) -> bool:
    if color.alpha() == 0:
        return False
    r, g, b = color.red(), color.green(), color.blue()
    if r >= 255 - tolerance and g >= 255 - tolerance and b >= 255 - tolerance:
        return True
    if r >= 235 and g >= 225 and b >= 200 and (r - b) <= 45:
        return True
    return False


def _corners_transparent(image: QImage, *, alpha_max: int = 16) -> bool:
    w, h = image.width(), image.height()
    if w == 0 or h == 0:
        return False
    corners = ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))
    return all(image.pixelColor(x, y).alpha() <= alpha_max for x, y in corners)


def _downscale_if_large(image: QImage, max_side: int) -> QImage:
    w, h = image.width(), image.height()
    if w <= max_side and h <= max_side:
        return image
    return image.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def knock_out_background(image: QImage, *, tolerance: int = 22) -> QImage:
    img = image.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    if w == 0 or h == 0:
        return img
    visited = bytearray(w * h)

    def visit(x: int, y: int) -> bool:
        return visited[y * w + x] != 0

    def mark(x: int, y: int) -> None:
        visited[y * w + x] = 1

    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not visit(x, y) and _is_knockout_background(img.pixelColor(x, y), tolerance=tolerance):
                mark(x, y)
                queue.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if not visit(x, y) and _is_knockout_background(img.pixelColor(x, y), tolerance=tolerance):
                mark(x, y)
                queue.append((x, y))

    transparent = QColor(0, 0, 0, 0)
    while queue:
        x, y = queue.popleft()
        img.setPixelColor(x, y, transparent)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not visit(nx, ny):
                if _is_knockout_background(img.pixelColor(nx, ny), tolerance=tolerance):
                    mark(nx, ny)
                    queue.append((nx, ny))
    return img


def _should_knock_out(image: QImage, mode: KnockOutMode) -> bool:
    if mode == "never":
        return False
    if mode == "always":
        return True
    argb = image.convertToFormat(QImage.Format_ARGB32)
    if _corners_transparent(argb):
        return False
    return True


def load_transparent_pixmap(path: str, *, knock_out: KnockOutMode = "auto") -> QPixmap:
    image = QImage(path)
    if image.isNull():
        return QPixmap()
    if _should_knock_out(image, knock_out):
        image = _downscale_if_large(image, KNOCKOUT_MAX_SIDE)
        image = knock_out_background(image)
    return QPixmap.fromImage(image.convertToFormat(QImage.Format_ARGB32))


def scale_to_square(pix: QPixmap, size: int) -> QPixmap:
    if pix.isNull() or size <= 0:
        return QPixmap()
    canvas = QPixmap(size, size)
    canvas.fill(Qt.transparent)
    scaled = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return canvas
