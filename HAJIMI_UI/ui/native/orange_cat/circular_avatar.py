"""Circular avatar label — PNG/JPG/GIF."""
from __future__ import annotations

import os

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QBrush, QColor, QFont, QMovie, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QLabel

from ui.native.orange_cat.icons import orange_cat_pixmap
from ui.native.orange_cat.image_alpha import load_transparent_pixmap
from ui.native.orange_cat.image_pool import default_ai_avatar_path, default_user_avatar_path
from ui.native.orange_cat.palettes import production_palette
from ui.native.orange_cat.tokens import PRIMARY, PRIMARY_DARK

AVATAR_SIZE = 36
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _is_gif(path: str) -> bool:
    return path.lower().endswith(".gif")


def _is_image_file(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    return os.path.splitext(path)[1].lower() in _IMAGE_EXTS


class CircularAvatar(QLabel):
    """Round avatar; static images clipped in paintEvent, GIF via QMovie frames."""

    def __init__(self, role: str = "ai", parent=None):
        super().__init__(parent)
        self._role = role if role in ("ai", "user") else "ai"
        self.setObjectName("BubbleAvatar")
        self.setProperty("avatarRole", self._role)
        self.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._static_pixmap: QPixmap | None = None
        self._movie: QMovie | None = None
        self._custom_path: str | None = None
        self._fallback_pixmap = self._build_fallback()

    def _build_fallback(self) -> QPixmap:
        if self._role == "ai":
            mark = orange_cat_pixmap("mark", AVATAR_SIZE)
            if not mark.isNull():
                return mark
            return orange_cat_pixmap("avatar", AVATAR_SIZE)
        pal = production_palette()
        pix = QPixmap(AVATAR_SIZE, AVATAR_SIZE)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(PRIMARY_DARK), 1.5))
        p.setBrush(QColor(pal.bg_warm))
        p.drawEllipse(1, 1, AVATAR_SIZE - 2, AVATAR_SIZE - 2)
        font = QFont("Segoe UI", 11, QFont.Bold)
        p.setFont(font)
        p.setPen(QColor(pal.text_primary))
        p.drawText(pix.rect(), Qt.AlignCenter, "我")
        p.end()
        return pix

    def _stop_movie(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie.setParent(None)
            self._movie.deleteLater()
            self._movie = None

    def _current_frame(self) -> QPixmap:
        if self._movie is not None:
            frame = self._movie.currentPixmap()
            if not frame.isNull():
                return frame
        if self._static_pixmap is not None and not self._static_pixmap.isNull():
            return self._static_pixmap
        return self._fallback_pixmap

    def set_image_path(self, path: str | None) -> None:
        self._stop_movie()
        self._static_pixmap = None
        self._custom_path = None
        if path and _is_image_file(path):
            self._custom_path = path
            if _is_gif(path):
                movie = QMovie(path)
                movie.setBackgroundColor(QColor(0, 0, 0, 0))
                movie.setScaledSize(QSize(AVATAR_SIZE, AVATAR_SIZE))
                movie.frameChanged.connect(lambda _i: self.update())
                movie.start()
                self._movie = movie
            else:
                pix = load_transparent_pixmap(path)
                if not pix.isNull():
                    self._static_pixmap = pix
        self.update()

    def clear_custom(self) -> None:
        self.set_image_path(None)

    def paintEvent(self, event):
        side = min(self.width(), self.height())
        if side <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        clip = QPainterPath()
        clip.addEllipse(0, 0, side, side)
        painter.setClipPath(clip)
        src = self._current_frame()
        scaled = src.scaled(
            side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        x = (side - scaled.width()) // 2
        y = (side - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.setClipping(False)
        border = QColor(PRIMARY_DARK if self._role == "user" else PRIMARY)
        border.setAlpha(90)
        painter.setPen(QPen(border, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(1, 1, side - 2, side - 2)
        painter.end()


def resolve_avatar_path(role: str) -> str:
    if role == "user":
        return default_user_avatar_path() or ""
    return default_ai_avatar_path() or ""


def render_ai_avatar_pixmap(size: int = 32) -> QPixmap:
    """Round AI avatar for compact bar — same source as medium chat."""
    side = max(16, int(size))
    path = resolve_avatar_path("system")
    frame: QPixmap | None = None
    if path and _is_image_file(path):
        if _is_gif(path):
            movie = QMovie(path)
            movie.setScaledSize(QSize(side, side))
            movie.jumpToFrame(0)
            frame = movie.currentPixmap()
            movie.setParent(None)
            movie.deleteLater()
        else:
            loaded = load_transparent_pixmap(path)
            if not loaded.isNull():
                frame = loaded
    if frame is None or frame.isNull():
        tmp = CircularAvatar("ai")
        frame = tmp._fallback_pixmap
    out = QPixmap(side, side)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    clip = QPainterPath()
    clip.addEllipse(0, 0, side, side)
    painter.setClipPath(clip)
    scaled = frame.scaled(
        side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )
    x = (side - scaled.width()) // 2
    y = (side - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.setClipping(False)
    border = QColor(PRIMARY)
    border.setAlpha(120)
    painter.setPen(QPen(border, 2))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(1, 1, side - 2, side - 2)
    painter.end()
    return out
