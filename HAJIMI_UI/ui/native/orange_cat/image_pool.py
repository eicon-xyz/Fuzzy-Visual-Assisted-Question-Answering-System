"""Bundled orange cat assets — photos, icons, sounds."""
from __future__ import annotations

import os
import random
from pathlib import Path

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_ICON_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

ICON_STEMS = frozenset(
    {
        "mark",
        "menu",
        "mic",
        "send",
        "badge",
        "avatar",
        "guide",
        "steps",
        "blueprint",
        "notifications",
        "settings",
        "compact",
        "logout",
        "compactmark",
    }
)

ICON_STEM_ALIASES: dict[str, tuple[str, ...]] = {
    "mark": ("mark", "compactmark"),
    "avatar": ("avatar", "ai"),
}

DEFAULT_SPLASH_STEMS = ("start", "default")
DEFAULT_AI_AVATAR_STEMS = ("ai", "avatar")
DEFAULT_USER_AVATAR_STEMS = ("me", "user")
DESKTOP_ICON_STEMS = ("app_icon", "desktop", "mark", "compactmark")
SPLASH_EXCLUDED_STEMS = ICON_STEMS | frozenset({"ai", "me", "user"})

_user_folder: str = ""
_default_image: str = ""
_ai_avatar_override: str = ""
_user_avatar_override: str = ""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def bundled_dir() -> Path:
    return _repo_root() / "assets" / "themes" / "orange_cat" / "photos"


def bundled_icons_dir() -> Path:
    return _repo_root() / "assets" / "themes" / "orange_cat" / "icons"


def set_user_folder(path: str) -> None:
    global _user_folder
    _user_folder = (path or "").strip()


def user_folder() -> str:
    return _user_folder


def set_default_image(path: str) -> None:
    global _default_image
    _default_image = (path or "").strip()


def default_image() -> str:
    return _default_image


def set_ai_avatar_path(path: str) -> None:
    global _ai_avatar_override
    _ai_avatar_override = (path or "").strip()


def set_user_avatar_path(path: str) -> None:
    global _user_avatar_override
    _user_avatar_override = (path or "").strip()


def apply_avatar_settings(data: dict | None = None) -> None:
    """Inject persisted avatar paths (preferred over bundled scan)."""
    if data is None:
        try:
            from core.user_settings import load_user_settings

            data = load_user_settings()
        except Exception:
            data = {}
    set_ai_avatar_path(str(data.get("orange_cat_ai_avatar") or ""))
    set_user_avatar_path(str(data.get("orange_cat_user_avatar") or ""))


def _asset_search_dirs(*, include_legacy_icons: bool = False) -> list[Path]:
    dirs: list[Path] = []
    if _user_folder:
        dirs.append(Path(_user_folder))
    dirs.append(bundled_dir())
    if include_legacy_icons:
        legacy = bundled_icons_dir()
        if legacy not in dirs:
            dirs.append(legacy)
    return dirs


def _icon_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    if _user_folder:
        uf = Path(_user_folder)
        user_icons = uf / "icons"
        if user_icons.is_dir():
            dirs.append(user_icons)
    dirs.append(bundled_icons_dir())
    if _user_folder:
        uf = Path(_user_folder)
        if uf not in dirs:
            dirs.append(uf)
    photos = bundled_dir()
    if photos not in dirs:
        dirs.append(photos)
    return dirs


def _avatar_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    if _user_folder:
        dirs.append(Path(_user_folder))
    photos = bundled_dir()
    if photos not in dirs:
        dirs.append(photos)
    icons = bundled_icons_dir()
    if icons not in dirs:
        dirs.append(icons)
    return dirs


def _find_by_stems(
    stems: tuple[str, ...],
    *,
    exts: tuple[str, ...] = _IMAGE_EXTS,
    include_legacy_icons: bool = False,
) -> str | None:
    for folder in _asset_search_dirs(include_legacy_icons=include_legacy_icons):
        if not folder.is_dir():
            continue
        for stem in stems:
            for ext in exts:
                path = folder / f"{stem}{ext}"
                if path.is_file():
                    return str(path.resolve())
            stem_lower = stem.lower()
            for entry in folder.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in exts:
                    continue
                if entry.stem.lower() == stem_lower:
                    return str(entry.resolve())
    return None


def default_splash_path() -> str | None:
    return _find_by_stems(DEFAULT_SPLASH_STEMS)


def default_ai_avatar_path() -> str | None:
    if _ai_avatar_override and os.path.isfile(_ai_avatar_override):
        return os.path.abspath(_ai_avatar_override)
    for folder in _avatar_search_dirs():
        if not folder.is_dir():
            continue
        for stems in (DEFAULT_AI_AVATAR_STEMS, ("ai",)):
            for stem in stems:
                for ext in _IMAGE_EXTS:
                    path = folder / f"{stem}{ext}"
                    if path.is_file():
                        return str(path.resolve())
                stem_lower = stem.lower()
                for entry in folder.iterdir():
                    if not entry.is_file():
                        continue
                    if entry.suffix.lower() not in _IMAGE_EXTS:
                        continue
                    if entry.stem.lower() == stem_lower:
                        return str(entry.resolve())
    return None


def default_user_avatar_path() -> str | None:
    if _user_avatar_override and os.path.isfile(_user_avatar_override):
        return os.path.abspath(_user_avatar_override)
    return _find_by_stems(DEFAULT_USER_AVATAR_STEMS, exts=_IMAGE_EXTS)


def default_desktop_icon_path() -> str | None:
    return _find_by_stems(DESKTOP_ICON_STEMS, include_legacy_icons=True)


def resolve_icon_path(name: str) -> str | None:
    stem = (name or "").strip()
    if not stem:
        return None
    candidates = ICON_STEM_ALIASES.get(stem, (stem,))
    for folder in _icon_search_dirs():
        if not folder.is_dir():
            continue
        for candidate in candidates:
            for ext in _ICON_EXTS:
                path = folder / f"{candidate}{ext}"
                if path.is_file():
                    return str(path.resolve())
            candidate_lower = candidate.lower()
            for entry in folder.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in _ICON_EXTS:
                    continue
                if entry.stem.lower() == candidate_lower:
                    return str(entry.resolve())
    return None


def _is_splash_candidate(path: str) -> bool:
    return Path(path).stem.lower() not in SPLASH_EXCLUDED_STEMS


def _scan_dir(folder: Path, *, splash_only: bool = False) -> list[str]:
    if not folder.is_dir():
        return []
    out: list[str] = []
    for name in sorted(folder.iterdir()):
        if not name.is_file() or name.suffix.lower() not in _IMAGE_EXTS:
            continue
        resolved = str(name.resolve())
        if splash_only and not _is_splash_candidate(resolved):
            continue
        out.append(resolved)
    return out


def pool_paths() -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for folder in (bundled_dir(), Path(_user_folder) if _user_folder else None):
        if folder is None:
            continue
        for p in _scan_dir(folder, splash_only=True):
            if p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


def pick_image() -> str | None:
    default = _default_image
    if default and os.path.isfile(default):
        return default
    bundled = default_splash_path()
    if bundled:
        return bundled
    pool = pool_paths()
    if not pool:
        return None
    return random.choice(pool)
