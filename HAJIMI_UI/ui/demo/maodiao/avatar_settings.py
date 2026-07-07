"""Demo chat avatar path overrides — wraps production defaults."""
from __future__ import annotations

from ui.native.orange_cat.image_pool import default_ai_avatar_path, default_user_avatar_path

_ai_avatar_path: str = ""
_user_avatar_path: str = ""


def set_ai_avatar(path: str) -> None:
    global _ai_avatar_path
    _ai_avatar_path = (path or "").strip()


def set_user_avatar(path: str) -> None:
    global _user_avatar_path
    _user_avatar_path = (path or "").strip()


def ai_avatar_path() -> str:
    if _ai_avatar_path:
        return _ai_avatar_path
    return default_ai_avatar_path() or ""


def user_avatar_path() -> str:
    if _user_avatar_path:
        return _user_avatar_path
    return default_user_avatar_path() or ""


def clear_ai_avatar() -> None:
    set_ai_avatar("")


def clear_user_avatar() -> None:
    set_user_avatar("")
