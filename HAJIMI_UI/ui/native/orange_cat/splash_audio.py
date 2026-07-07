"""Splash audio paths."""
from __future__ import annotations

import os
from pathlib import Path

_AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac")

DEFAULT_SPLASH_AUDIO_STEMS = ("start", "splash")

_custom_splash_audio: str = ""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def bundled_sounds_dir() -> Path:
    return _repo_root() / "assets" / "themes" / "orange_cat" / "sounds"


def set_splash_audio(path: str) -> None:
    global _custom_splash_audio
    _custom_splash_audio = (path or "").strip()


def clear_splash_audio() -> None:
    set_splash_audio("")


def custom_splash_audio() -> str:
    return _custom_splash_audio


def _find_audio_in_dir(folder: Path) -> str | None:
    if not folder.is_dir():
        return None
    for stem in DEFAULT_SPLASH_AUDIO_STEMS:
        for ext in _AUDIO_EXTS:
            path = folder / f"{stem}{ext}"
            if path.is_file():
                return str(path.resolve())
        stem_lower = stem.lower()
        for entry in folder.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in _AUDIO_EXTS:
                continue
            if entry.stem.lower() == stem_lower:
                return str(entry.resolve())
    return None


def default_splash_audio_path() -> str | None:
    return _find_audio_in_dir(bundled_sounds_dir())


def resolve_splash_audio_path(settings_path: str = "") -> str | None:
    custom = (settings_path or "").strip() or _custom_splash_audio
    if custom and os.path.isfile(custom):
        return custom
    return default_splash_audio_path()
