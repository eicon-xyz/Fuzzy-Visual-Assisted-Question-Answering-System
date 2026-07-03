"""
Windows window enumeration via Win32 API.

Python equivalent of OpenGuider's perception/window-enum.js.
Instead of PowerShell scripts (EnumWindows, GetForegroundWindow),
we use ctypes to call Win32 APIs directly. This is faster and
eliminates the PowerShell dependency.

Returns visible window list + focused window + cursor position.
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# ── Win32 API definitions ─────────────────────────────────────────────────────

user32 = ctypes.windll.user32

# Window enumeration callback type
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# Functions
enum_windows = user32.EnumWindows
enum_windows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
enum_windows.restype = wintypes.BOOL

is_window_visible = user32.IsWindowVisible
is_window_visible.argtypes = [wintypes.HWND]
is_window_visible.restype = wintypes.BOOL

get_window_text_length = user32.GetWindowTextLengthW
get_window_text_length.argtypes = [wintypes.HWND]
get_window_text_length.restype = ctypes.c_int

get_window_text = user32.GetWindowTextW
get_window_text.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
get_window_text.restype = ctypes.c_int

get_window_thread_process_id = user32.GetWindowThreadProcessId
get_window_thread_process_id.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
get_window_thread_process_id.restype = wintypes.DWORD

is_iconic = user32.IsIconic
is_iconic.argtypes = [wintypes.HWND]
is_iconic.restype = wintypes.BOOL

get_foreground_window = user32.GetForegroundWindow
get_foreground_window.argtypes = []
get_foreground_window.restype = wintypes.HWND

get_class_name = user32.GetClassNameW
get_class_name.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
get_class_name.restype = ctypes.c_int


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


get_window_rect = user32.GetWindowRect
get_window_rect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
get_window_rect.restype = wintypes.BOOL


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


get_cursor_pos = user32.GetCursorPos
get_cursor_pos.argtypes = [ctypes.POINTER(POINT)]
get_cursor_pos.restype = wintypes.BOOL


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class WindowRecord:
    """A single visible window."""
    hwnd: int = 0
    title: str = ""
    pid: int = 0
    class_name: str = ""
    minimized: bool = False
    rect: dict = field(default_factory=lambda: {
        "x": 0, "y": 0, "width": 0, "height": 0,
    })


@dataclass
class WindowInfo:
    """Aggregated window state snapshot."""
    focused_window: Optional[WindowRecord] = None
    windows: List[WindowRecord] = field(default_factory=list)
    cursor_position: Tuple[int, int] = (0, 0)


# ── Implementation ────────────────────────────────────────────────────────────


def _sanitize(s: str) -> str:
    """Strip control characters from window title."""
    if not s:
        return ""
    return "".join(ch for ch in s if ord(ch) >= 32)


def get_active_windows() -> List[WindowRecord]:
    """Enumerate all visible top-level windows via EnumWindows.

    Maps to OpenGuider's window-enum.js getActiveWindows().

    Returns:
        List of WindowRecord for visible, titled windows
    """
    windows = []

    def callback(hwnd, lparam):
        if not is_window_visible(hwnd):
            return True  # continue enumeration

        # Get window title
        length = get_window_text_length(hwnd)
        if length == 0:
            return True

        buf = ctypes.create_unicode_buffer(length + 1)
        get_window_text(hwnd, buf, length + 1)
        title = buf.value
        if not title or not title.strip():
            return True

        # Skip IME windows
        cls_buf = ctypes.create_unicode_buffer(256)
        get_class_name(hwnd, cls_buf, 256)
        class_name = cls_buf.value or ""
        if class_name in ("IME", "MSCTFIME UI"):
            return True

        # Get PID
        pid = wintypes.DWORD()
        get_window_thread_process_id(hwnd, ctypes.byref(pid))

        # Get rect
        rect = RECT()
        if get_window_rect(hwnd, ctypes.byref(rect)):
            win_rect = {
                "x": rect.left,
                "y": rect.top,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
            }
        else:
            win_rect = {"x": 0, "y": 0, "width": 0, "height": 0}

        # Check minimized
        minimized = bool(is_iconic(hwnd))

        windows.append(WindowRecord(
            hwnd=hwnd,
            title=_sanitize(title),
            pid=pid.value,
            class_name=class_name,
            minimized=minimized,
            rect=win_rect,
        ))
        return True

    cb = WNDENUMPROC(callback)
    try:
        enum_windows(cb, 0)
    except Exception as e:
        logger.error(f"EnumWindows failed: {e}")

    return windows


def get_focused_window() -> Optional[WindowRecord]:
    """Get the currently focused/foreground window.

    Maps to OpenGuider's window-enum.js getFocusedWindow().

    Returns:
        WindowRecord for focused window, or None
    """
    hwnd = get_foreground_window()
    if not hwnd:
        return None

    # Get title
    length = get_window_text_length(hwnd)
    title = ""
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        get_window_text(hwnd, buf, length + 1)
        title = buf.value or ""

    # Get PID
    pid = wintypes.DWORD()
    get_window_thread_process_id(hwnd, ctypes.byref(pid))

    # Get rect
    rect = RECT()
    if get_window_rect(hwnd, ctypes.byref(rect)):
        win_rect = {
            "x": rect.left,
            "y": rect.top,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        }
    else:
        win_rect = {"x": 0, "y": 0, "width": 0, "height": 0}

    return WindowRecord(
        hwnd=hwnd,
        title=_sanitize(title),
        pid=pid.value,
        class_name="",
        minimized=bool(is_iconic(hwnd)),
        rect=win_rect,
    )


def get_cursor_position() -> Tuple[int, int]:
    """Get current mouse cursor screen position.

    Maps to OpenGuider's window-enum.js getCursorPosition().

    Returns:
        (x, y) tuple of cursor coordinates
    """
    point = POINT()
    if get_cursor_pos(ctypes.byref(point)):
        return (point.x, point.y)
    return (0, 0)


def enumerate_active_app() -> WindowInfo:
    """Get complete window state snapshot.

    Runs focused window detection, window enumeration, and cursor
    position query in parallel-like fashion (sequential is fine in Python
    since these are sub-millisecond ctypes calls).

    Maps to OpenGuider's window-enum.js enumerateActiveApp().

    Returns:
        WindowInfo with focused_window, windows (max 30), cursor_position
    """
    focused = get_focused_window()
    windows = get_active_windows()
    cursor = get_cursor_position()

    # Limit to top 30 windows by title (visible ones first, filtered)
    visible = [w for w in windows if not w.minimized]
    minimized = [w for w in windows if w.minimized]
    top_windows = (visible + minimized)[:30]

    result = WindowInfo(
        focused_window=focused,
        windows=top_windows,
        cursor_position=cursor,
    )

    if focused:
        logger.debug(f"Focused: '{focused.title}' hwnd={focused.hwnd}")
    logger.debug(
        f"Windows: {len(top_windows)} visible, "
        f"cursor: ({cursor[0]}, {cursor[1]})"
    )

    return result
