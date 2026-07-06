"""Persist main window geometry and mode to local JSON."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QRect
from PyQt5.QtWidgets import QApplication, QWidget

from config import MEDIUM_WIDTH, MEDIUM_HEIGHT, COMPACT_WIDTH
from ui.native.layout_tokens import (
    MEDIUM_MIN_H,
    MEDIUM_MIN_W,
    COMPACT_MIN_W,
    COMPACT_MAX_W,
)
from ui.native.window_clip import clamp_geometry_to_screen

# Previous default before 480×520 layout alignment
_LEGACY_MEDIUM_SIZES = frozenset({(370, 540)})


def _state_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "HAJIMI")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "window_state.json")


@dataclass
class WindowState:
    medium_width: int
    medium_height: int
    x: Optional[int] = None
    y: Optional[int] = None
    last_mode: str = "medium"
    compact_width: int = COMPACT_WIDTH
    migrated_from_legacy: bool = False


def _screen_max() -> tuple[int, int]:
    screen = QApplication.primaryScreen()
    if not screen:
        return 1920, 1080
    area = screen.availableGeometry()
    return int(area.width() * 0.9), int(area.height() * 0.9)


def clamp_size(width: int, height: int) -> tuple[int, int]:
    max_w, max_h = _screen_max()
    w = max(MEDIUM_MIN_W, min(max_w, int(width)))
    h = max(MEDIUM_MIN_H, min(max_h, int(height)))
    return w, h


def clamp_compact_width(width: int) -> int:
    return max(COMPACT_MIN_W, min(COMPACT_MAX_W, int(width)))


def load_window_state() -> Optional[WindowState]:
    path = _state_path()
    if not os.path.isfile(path):
        return None
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        raw_w = int(data.get("medium_width", MEDIUM_WIDTH))
        raw_h = int(data.get("medium_height", MEDIUM_HEIGHT))
        migrated = (raw_w, raw_h) in _LEGACY_MEDIUM_SIZES
        if migrated:
            w, h = clamp_size(MEDIUM_WIDTH, MEDIUM_HEIGHT)
        else:
            w, h = clamp_size(raw_w, raw_h)
        compact_w = clamp_compact_width(
            int(data.get("compact_width", COMPACT_WIDTH))
        )
        x = data.get("x")
        y = data.get("y")
        mode = data.get("last_mode", "medium")
        if mode not in ("medium", "compact"):
            mode = "medium"
        return WindowState(
            medium_width=w,
            medium_height=h,
            x=int(x) if x is not None else None,
            y=int(y) if y is not None else None,
            last_mode=mode,
            compact_width=compact_w,
            migrated_from_legacy=migrated,
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_window_state(
    medium_width: int,
    medium_height: int,
    x: int,
    y: int,
    last_mode: str,
    *,
    compact_width: int = COMPACT_WIDTH,
) -> None:
    w, h = clamp_size(medium_width, medium_height)
    cw = clamp_compact_width(compact_width)
    payload = {
        "medium_width": w,
        "medium_height": h,
        "compact_width": cw,
        "x": int(x),
        "y": int(y),
        "last_mode": last_mode if last_mode in ("medium", "compact") else "medium",
    }
    path = _state_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def apply_state_to_window(window: QWidget, state: WindowState) -> None:
    w, h = clamp_size(state.medium_width, state.medium_height)
    if state.x is not None and state.y is not None:
        geo = clamp_geometry_to_screen(QRect(state.x, state.y, w, h))
        window.setGeometry(geo)
    else:
        window.resize(w, h)
