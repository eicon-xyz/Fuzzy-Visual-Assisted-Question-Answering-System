"""Fullscreen splash animation — separate overlay window."""
from __future__ import annotations

import os
import time

from PyQt5.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt5.QtGui import QMovie, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget

from ui.native.orange_cat.tokens import (
    DEFAULT_FADE_OUT_MS,
    DEFAULT_HOLD_MS,
    DEFAULT_SCALE_IN_MS,
)

SPLASH_BASE_RATIO = 1.10
SPLASH_MAX_SCREEN_RATIO = 0.92
FADE_OUT_SCALE_EXTRA = 1.40

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _is_gif(path: str) -> bool:
    return path.lower().endswith(".gif")


def _is_image_file(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    return os.path.splitext(path)[1].lower() in _IMAGE_EXTS


class OrangeCatSplashOverlay(QWidget):
    """Center scale-in → hold → scale-out + fade. Mouse-transparent."""

    finished = pyqtSignal()
    fade_out_started = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._pixmap = QPixmap()
        self._movie: QMovie | None = None
        self._scale = 0.15
        self._opacity = 0.0
        self._phase = "idle"
        self._phase_start = 0.0
        self._scale_in_ms = DEFAULT_SCALE_IN_MS
        self._hold_ms = DEFAULT_HOLD_MS
        self._fade_out_ms = DEFAULT_FADE_OUT_MS
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def _stop_movie(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie.setParent(None)
            self._movie.deleteLater()
            self._movie = None

    def _current_pixmap(self) -> QPixmap:
        if self._movie is not None:
            frame = self._movie.currentPixmap()
            if not frame.isNull():
                return frame
        return self._pixmap

    def play(
        self,
        image_path: str,
        *,
        scale_in_ms: int | None = None,
        hold_ms: int | None = None,
        fade_out_ms: int | None = None,
    ) -> bool:
        self._stop_movie()
        self._pixmap = QPixmap()
        if not _is_image_file(image_path):
            return False
        screen = QApplication.primaryScreen()
        if not screen:
            return False

        if _is_gif(image_path):
            movie = QMovie(image_path)
            if not movie.isValid():
                return False
            movie.frameChanged.connect(lambda _i: self.update())
            movie.start()
            self._movie = movie
            if self._current_pixmap().isNull():
                self._stop_movie()
                return False
        else:
            pix = QPixmap(image_path)
            if pix.isNull():
                return False
            self._pixmap = pix

        self._scale_in_ms = max(1, scale_in_ms if scale_in_ms is not None else DEFAULT_SCALE_IN_MS)
        self._hold_ms = max(0, hold_ms if hold_ms is not None else DEFAULT_HOLD_MS)
        self._fade_out_ms = max(1, fade_out_ms if fade_out_ms is not None else DEFAULT_FADE_OUT_MS)
        self._scale = 0.15
        self._opacity = 0.0
        self._phase = "scale_in"
        self._phase_start = time.monotonic()
        geo = screen.geometry()
        self.setGeometry(geo)
        self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start()
        self._tick()
        return True

    def _ease_out_cubic(self, t: float) -> float:
        t = max(0.0, min(1.0, t))
        return 1.0 - pow(1.0 - t, 3)

    def _tick(self) -> None:
        if self._current_pixmap().isNull():
            self._finish()
            return
        now = time.monotonic()
        elapsed_ms = (now - self._phase_start) * 1000.0

        if self._phase == "scale_in":
            t = elapsed_ms / self._scale_in_ms
            if t >= 1.0:
                self._scale = 1.0
                self._opacity = 1.0
                self._phase = "hold"
                self._phase_start = now
            else:
                e = self._ease_out_cubic(t)
                self._scale = 0.15 + (1.0 - 0.15) * e
                self._opacity = e
        elif self._phase == "hold":
            self._scale = 1.0
            self._opacity = 1.0
            if elapsed_ms >= self._hold_ms:
                self._phase = "fade_out"
                self._phase_start = now
                self.fade_out_started.emit(self._fade_out_ms)
        elif self._phase == "fade_out":
            t = elapsed_ms / self._fade_out_ms
            if t >= 1.0:
                self._finish()
                return
            self._scale = 1.0 + FADE_OUT_SCALE_EXTRA * t
            self._opacity = max(0.0, 1.0 - t)
        else:
            return
        self.update()

    def _finish(self) -> None:
        self._timer.stop()
        self._stop_movie()
        self._phase = "idle"
        self._pixmap = QPixmap()
        self.hide()
        self.finished.emit()

    def paintEvent(self, event):
        pix = self._current_pixmap()
        if pix.isNull() or self._opacity <= 0.001:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(self._opacity)
        w = self.width()
        h = self.height()
        base = min(w, h) * SPLASH_BASE_RATIO
        cap = min(w, h) * SPLASH_MAX_SCREEN_RATIO
        base = min(base, cap)
        tw = int(base * self._scale)
        th = int(base * self._scale * pix.height() / max(1, pix.width()))
        x = (w - tw) // 2
        y = (h - th) // 2
        target = QRectF(x, y, tw, th)
        painter.drawPixmap(target.toRect(), pix)
        painter.end()


MaodiaoSplashOverlay = OrangeCatSplashOverlay
