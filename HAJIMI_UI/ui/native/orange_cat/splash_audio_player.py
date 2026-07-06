"""Play splash sound with preload and fade-out sync."""
from __future__ import annotations

from PyQt5.QtCore import QObject, QPropertyAnimation, QUrl, pyqtProperty

try:
    from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

    _HAS_MEDIA = True
    _LOADED_STATUSES = frozenset(
        {
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.BufferedMedia,
            QMediaPlayer.EndOfMedia,
        }
    )
except ImportError:
    QMediaContent = None  # type: ignore[misc, assignment]
    QMediaPlayer = None  # type: ignore[misc, assignment]
    _HAS_MEDIA = False
    _LOADED_STATUSES = frozenset()


class _VolumeProxy(QObject):
    def __init__(self, player: QMediaPlayer | None, parent=None):
        super().__init__(parent)
        self._player = player
        self._volume = 85

    def getVolume(self) -> int:
        return self._volume

    def setVolume(self, value: int) -> None:
        self._volume = max(0, min(100, int(value)))
        if self._player is not None:
            self._player.setVolume(self._volume)

    volume = pyqtProperty(int, getVolume, setVolume)


class SplashAudioPlayer(QObject):
    DEFAULT_VOLUME = 85

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player: QMediaPlayer | None = None
        self._volume_proxy: _VolumeProxy | None = None
        self._fade_anim: QPropertyAnimation | None = None
        self._loaded_path = ""
        self._pending_play = False
        self._base_volume = self.DEFAULT_VOLUME
        if _HAS_MEDIA:
            self._player = QMediaPlayer(self)
            self._volume_proxy = _VolumeProxy(self._player, self)
            self._player.mediaStatusChanged.connect(self._on_media_status)

    def preload(self, path: str | None) -> None:
        if not path or self._player is None:
            return
        resolved = str(path)
        if resolved == self._loaded_path and self._is_loaded():
            return
        self._cancel_fade()
        self._pending_play = False
        self._loaded_path = resolved
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(resolved)))

    def play(self, path: str | None, *, volume: int = 85) -> None:
        if not path or self._player is None:
            return
        resolved = str(path)
        self._base_volume = max(0, min(100, volume))
        self._cancel_fade()
        if self._player.state() == QMediaPlayer.PlayingState:
            self._player.stop()
        self._pending_play = True
        if resolved != self._loaded_path or not self._is_loaded():
            self._loaded_path = resolved
            self._player.setMedia(QMediaContent(QUrl.fromLocalFile(resolved)))
        else:
            self._start_playback()

    def begin_fade_out(self, fade_ms: int) -> None:
        if self._player is None or self._volume_proxy is None:
            return
        if self._player.state() != QMediaPlayer.PlayingState:
            return
        self._cancel_fade()
        duration = max(1, int(fade_ms))
        start_vol = self._player.volume()
        self._volume_proxy.setVolume(start_vol)
        anim = QPropertyAnimation(self._volume_proxy, b"volume", self)
        anim.setDuration(duration)
        anim.setStartValue(start_vol)
        anim.setEndValue(0)
        anim.finished.connect(self._on_fade_finished)
        self._fade_anim = anim
        anim.start()

    def stop(self) -> None:
        if self._player is None:
            return
        self._cancel_fade()
        self._pending_play = False
        self._player.stop()
        if self._volume_proxy is not None:
            self._volume_proxy.setVolume(self._base_volume)

    def _is_loaded(self) -> bool:
        if self._player is None:
            return False
        return self._player.mediaStatus() in _LOADED_STATUSES

    def _on_media_status(self, status) -> None:
        if not self._pending_play or self._player is None:
            return
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            self._start_playback()

    def _start_playback(self) -> None:
        if self._player is None:
            return
        self._pending_play = False
        self._player.setPosition(0)
        if self._volume_proxy is not None:
            self._volume_proxy.setVolume(self._base_volume)
        self._player.play()

    def _cancel_fade(self) -> None:
        if self._fade_anim is None:
            return
        self._fade_anim.stop()
        self._fade_anim.deleteLater()
        self._fade_anim = None

    def _on_fade_finished(self) -> None:
        self._fade_anim = None
        if self._player is not None:
            self._player.stop()
        if self._volume_proxy is not None:
            self._volume_proxy.setVolume(self._base_volume)
