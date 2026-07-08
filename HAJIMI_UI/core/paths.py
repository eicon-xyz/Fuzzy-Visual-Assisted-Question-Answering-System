"""Repository-relative paths shared by Python code.

Bat scripts cannot import this module; keep scripts\\*.bat L5_ROOT in sync manually.
"""

from __future__ import annotations

import warnings
from pathlib import Path

# HAJIMI_UI/
ROOT = Path(__file__).resolve().parent.parent
# repo root (parent of HAJIMI_UI)
REPO_ROOT = ROOT.parent

L5_ROOT_FLAT = ("server_A",)
L5_ROOT_NESTED = ("server_A", "server_A")
LEGACY_L5_ROOT_SEGMENTS = ("new_JIMI", "HAJIMI_UI")


def _has_sidecar_marker(path: Path) -> bool:
    return (path / "scripts" / "start_server.bat").is_file()


def _candidate_l5_roots() -> list[Path]:
    return [
        REPO_ROOT.joinpath(*L5_ROOT_FLAT),
        REPO_ROOT.joinpath(*L5_ROOT_NESTED),
        REPO_ROOT.joinpath(*LEGACY_L5_ROOT_SEGMENTS),
    ]


def resolve_l5_root() -> Path:
    """A-end L5 Sidecar root; HAJIMI_L5_ROOT env overrides defaults."""
    import os

    try:
        from config import HAJIMI_L5_ROOT
    except Exception:
        HAJIMI_L5_ROOT = ""

    env = (HAJIMI_L5_ROOT or os.environ.get("HAJIMI_L5_ROOT", "")).strip()
    if env:
        return Path(env).resolve()

    preferred_flat = REPO_ROOT.joinpath(*L5_ROOT_FLAT)
    legacy = REPO_ROOT.joinpath(*LEGACY_L5_ROOT_SEGMENTS)
    for candidate in _candidate_l5_roots():
        if not _has_sidecar_marker(candidate):
            continue
        if candidate.resolve() == legacy.resolve():
            warnings.warn(
                f"Using deprecated L5 Sidecar path {legacy}; "
                f"prefer {preferred_flat} or set HAJIMI_L5_ROOT.",
                stacklevel=2,
            )
        return candidate.resolve()

    return preferred_flat.resolve()
