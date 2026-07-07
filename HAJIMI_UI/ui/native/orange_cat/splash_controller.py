"""Orange cat splash — startup and task-complete triggers."""
from __future__ import annotations

from PyQt5.QtCore import QTimer

from ui.native.orange_cat.image_pool import pick_image
from ui.native.orange_cat.splash_audio import resolve_splash_audio_path
from ui.native.orange_cat.splash_audio_player import SplashAudioPlayer
from ui.native.orange_cat.splash_overlay import OrangeCatSplashOverlay
from ui.native.orange_cat.tokens import (
    DEFAULT_FADE_OUT_MS,
    DEFAULT_HOLD_MS,
    DEFAULT_SCALE_IN_MS,
)
from ui.native.shell_appearance import AppearanceSettings, is_orange_cat_theme


class OrangeCatSplashController:
    """Play splash once on startup and on processing→idle when orange cat theme is active."""

    def __init__(self, parent):
        self._parent = parent
        self._overlay = OrangeCatSplashOverlay(parent)
        self._audio = SplashAudioPlayer(parent)
        self._overlay.fade_out_started.connect(self._fade_audio)
        self._overlay.finished.connect(self._stop_audio)
        self._startup_played = False
        self._prev_status = "idle"
        self._active = False
        self._appearance = AppearanceSettings()

    def apply_theme(self, theme_id: str, appearance: AppearanceSettings | None = None) -> None:
        self._appearance = appearance or AppearanceSettings()
        active = is_orange_cat_theme(theme_id)
        if active and not self._active:
            audio = resolve_splash_audio_path(self._appearance.orange_cat_splash_audio)
            if audio:
                self._audio.preload(audio)
        if not active:
            self._stop_all()
        self._active = active

    def on_window_shown(self, theme_id: str) -> None:
        if not is_orange_cat_theme(theme_id) or self._startup_played:
            return
        self._startup_played = True
        QTimer.singleShot(250, self._play)

    def on_status_updated(self, theme_id: str, status: str) -> None:
        if not is_orange_cat_theme(theme_id):
            self._prev_status = status
            return
        if self._prev_status == "processing" and status == "idle":
            self._play()
        self._prev_status = status

    def _play(self) -> None:
        if not self._active:
            return
        image = pick_image()
        if not image:
            return
        ok = self._overlay.play(
            image,
            scale_in_ms=DEFAULT_SCALE_IN_MS,
            hold_ms=DEFAULT_HOLD_MS,
            fade_out_ms=DEFAULT_FADE_OUT_MS,
        )
        if ok:
            audio = resolve_splash_audio_path(self._appearance.orange_cat_splash_audio)
            if audio:
                self._audio.play(audio)

    def _fade_audio(self, fade_ms: int) -> None:
        self._audio.begin_fade_out(fade_ms)

    def _stop_audio(self) -> None:
        self._audio.stop()

    def _stop_all(self) -> None:
        self._stop_audio()
        if self._overlay.isVisible():
            self._overlay.hide()
