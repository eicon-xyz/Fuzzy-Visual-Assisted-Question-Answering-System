"""
HAJIMI Screen Capture - self-window aware

Captures screen excluding HAJIMI's own windows (terminal, UI panel).
Uses win32gui to enumerate windows, mss for pixel capture, PIL for blackout.
"""
from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import List, Optional, Tuple

import mss
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Window title patterns to black out
_BLACKOUT_PATTERNS = [
    "HAJIMI",
    "hajimi",
    "uvicorn",
    "server.main:app",
    "Command Prompt",
    "cmd.exe",
    "Windows PowerShell",
    "powershell.exe",
    "bash",
    "MINGW",
    "msys2",
    "Terminal",
    "Python",
    "claude",
    "Claude",
    "chatglm",
    "ChatGLM",
    "Code",
    "cursor",
    "Cursor",
    "Visual Studio",
]


def _find_self_windows() -> List[Tuple[int, int, int, int]]:
    """Find rectangles of windows matching blackout patterns.
    Returns list of (left, top, right, bottom) in screen coordinates."""
    import win32gui

    rects: List[Tuple[int, int, int, int]] = []

    def callback(hwnd, _ctx):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return

            matched = any(p.lower() in title.lower() for p in _BLACKOUT_PATTERNS)
            if not matched:
                return

            rect = win32gui.GetWindowRect(hwnd)
            # Filter tiny or off-screen rects
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 100 or h < 50:
                return
            # Off-screen (minimized to virtual desktop)
            if rect[0] < -1000 or rect[1] < -1000:
                return
            rects.append(tuple(rect))
        except Exception:
            pass

    win32gui.EnumWindows(callback, None)
    return rects


def capture_screen() -> Optional[Image.Image]:
    """Capture primary monitor, black out self-windows. Returns RGB PIL Image."""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = Image.frombytes(
                "RGB", (monitor["width"], monitor["height"]),
                sct.grab(monitor).bgra, "raw", "BGRX",
            )

        blackouts = _find_self_windows()
        if blackouts:
            draw = ImageDraw.Draw(img)
            ml, mt = monitor.get("left", 0), monitor.get("top", 0)
            for left, top, right, bottom in blackouts:
                x1 = max(0, left - ml)
                y1 = max(0, top - mt)
                x2 = min(img.width, right - ml)
                y2 = min(img.height, bottom - mt)
                if x2 > x1 and y2 > y1:
                    draw.rectangle([x1, y1, x2, y2], fill="black")

        return img
    except Exception as e:
        logger.error(f"capture_screen: {e}")
        return None


def capture_to_base64(exclude_self: bool = True, fmt: str = "PNG") -> Optional[str]:
    """Capture screen, return 'data:image/...;base64,...' string.

    Args:
        exclude_self: Black out HAJIMI/dev windows
        fmt: 'PNG' (OmniParser) or 'JPEG' (LLM thumbnail)
    """
    if not exclude_self:
        try:
            with mss.mss() as sct:
                m = sct.monitors[1]
                img = mss.tools.to_png(sct.grab(m).rgb, m.size)
            return f"data:image/png;base64,{base64.b64encode(img).decode()}"
        except Exception:
            return None

    img = capture_screen()
    if img is None:
        return None

    if fmt == "JPEG":
        w, h = img.size
        if max(w, h) > 1024:
            r = 1024 / max(w, h)
            img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format=fmt, quality=75 if fmt == "JPEG" else None)
    b64 = base64.b64encode(buf.getvalue()).decode()
    mime = "image/jpeg" if fmt == "JPEG" else "image/png"
    return f"data:{mime};base64,{b64}"
