# -*- coding: utf-8 -*-
"""
Win+Search Application Launcher

Uses keyboard simulation + clipboard paste to open apps via Windows Start Menu.
No LLM. No OmniParser OCR. Just Win key + paste + Enter.

Based on UFO (Microsoft) project's approach of using system keyboard shortcuts
to launch applications deterministically.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# App name patterns for extracting target from user queries
_LAUNCH_PATTERNS = [
    # Chinese: "打开/启动/运行 XX"
    re.compile(
        r"(?:打开|启动|运行|开)\s*(?:一个|一下|下|这个|那个|帮我)?\s*[\"「']?([^\"「」'\s,，。\.]{1,40}?)[\"」']?\s*(?:然后|接着|再|并|$|，|,)",
        re.I,
    ),
    # English: "open/launch/start/run XX"
    re.compile(
        r"(?:open|launch|start|run)\s+(?:a|an|the|my)?\s*[\"「']?([^\"「」'\s,，。\.]{1,40}?)[\"」']?\s*(?:then|and|also|$|,)",
        re.I,
    ),
    # Bare app names: "VS Code", "Calculator" etc (two words max, no common non-app keywords)
    re.compile(
        r"^[\"「']?([A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z][A-Za-z0-9]*)?)[\"」']?\s*$", re.I
    ),
    # Short queries that look like app names (Chinese, no whitespace, no file/web keywords)
    re.compile(r"^[\"「']?([^\"「」'\s,，。\.]{1,30}?)[\"」']?\s*$", re.I),
]


def _extract_app_name_from_query(query: str) -> Optional[str]:
    """Extract target app name from a user query like 'open Notepad' or '打开网易云音乐，放首歌'.

    Returns the app name as-is (preserving language), or None if no launch pattern matches.
    """
    if not query:
        return None

    query = query.strip()

    for pat in _LAUNCH_PATTERNS:
        m = pat.search(query)
        if m:
            app = m.group(1).strip().rstrip("，,。.")
            if app and 1 <= len(app) <= 40:
                return app

    return None


def _extract_remaining_operation(query: str, app_name: str) -> Optional[str]:
    """Extract what to do after launching the app. E.g., '放首歌' from '打开网易云音乐，放首歌'.

    Returns None if the query is only about opening the app.
    """
    if not query or not app_name:
        return None

    # Try splitting on common continuations
    for sep in [
        "，然后",
        "，接着",
        "，再",
        "，",
        ", then",
        ", and",
        ", also",
        "然后",
        "接着",
        "再",
    ]:
        if sep in query:
            _, after = query.split(sep, 1)
            remaining = after.strip().rstrip("，,。.")
            if remaining and remaining != app_name:
                return remaining

    return None


def launch_app(app_name: str) -> dict:
    """Launch an application via Win+Search + Enter.

    Args:
        app_name: The application name to search for (preserves user's language).

    Returns:
        {"success": True, "app_name": str, "method": "win_search_enter"}
        or {"success": False, "app_name": str, "error": str}
    """
    from server.services.executor.clicker import press_keys

    if not app_name:
        return {"success": False, "app_name": app_name or "", "error": "empty app name"}

    logger.info(f"Launching '{app_name}' via Win+Search")

    # 1. Open Start Menu
    press_keys("win")
    time.sleep(0.3)

    # 2. Type search query via clipboard paste (bypasses IME issues)
    _paste_text(app_name)
    time.sleep(0.8)

    # 3. Press Enter to select the first search result
    # Windows Search ranks installed apps first, so the first result is
    # almost always the correct app (especially for exact-name searches)
    press_keys("enter")
    time.sleep(0.5)

    # 4. Close Start Menu in case Enter didn't work (prevent stale state)
    press_keys("esc")
    time.sleep(0.2)

    logger.info(f"Launched '{app_name}' successfully")

    # Wait for the app window to fully render before returning control.
    # Some apps (especially Electron-based ones) have rendering delays of
    # 500ms-1s; LLM taking a screenshot immediately may see a blank window.
    time.sleep(3)

    # Force foreground: find the launched app window and bring it to front.
    # This is critical for RDP/remote sessions where the app may not auto-focus.
    _force_window_foreground(app_name)

    return {"success": True, "app_name": app_name, "method": "win_search_enter"}


def _force_window_foreground(app_name: str) -> bool:
    """Find the app window by fuzzy title match and force it to the foreground.

    Uses pygetwindow for window enumeration and activation. Falls back to
    pywinauto if pygetwindow's activate() fails (e.g. in RDP sessions).

    Returns True if the window was found and activated.
    """
    try:
        import pygetwindow as gw
    except ImportError:
        logger.warning("pygetwindow not installed — cannot force window foreground")
        return False

    # Give the window a moment to appear
    time.sleep(0.5)

    # Collect candidate windows: exact title match first, then fuzzy
    candidates = gw.getWindowsWithTitle(app_name)
    if not candidates:
        # Fuzzy match: any window whose title contains any word from app_name
        app_words = app_name.lower().split()
        for win in gw.getAllWindows():
            title = (win.title or "").lower()
            if not title or title.startswith("_"):
                continue
            if any(word in title for word in app_words):
                candidates.append(win)

    if not candidates:
        logger.warning(
            f"_force_window_foreground: no window found matching '{app_name}'"
        )
        return False

    # Pick the largest visible window (most likely the main app window)
    best = None
    best_area = 0
    for w in candidates:
        area = w.width * w.height
        if area > best_area and not w.title.startswith("_"):
            best = w
            best_area = area

    if best is None:
        return False

    logger.info(
        f"_force_window_foreground: activating '{best.title}' ({best.width}x{best.height})"
    )

    try:
        # Try restore + activate (restore un-minimizes if needed)
        best.restore()
        time.sleep(0.2)
        best.activate()
        time.sleep(0.3)

        if best.isActive:
            logger.info(f"_force_window_foreground: '{best.title}' is now active")
            return True

        # Fallback: pygetwindow activate failed — try pywinauto
        logger.warning("pygetwindow activate failed, trying pywinauto fallback")
        try:
            from pywinauto import Desktop

            dlg = Desktop(backend="win32").window(title=best.title)
            dlg.set_focus()
            time.sleep(0.2)
            logger.info(
                f"_force_window_foreground: pywinauto set_focus succeeded on '{best.title}'"
            )
            return True
        except ImportError:
            logger.warning("pywinauto not installed — window may not be in foreground")
        except Exception as e:
            logger.warning(f"pywinauto fallback also failed: {e}")

        return best.isActive
    except Exception as e:
        logger.warning(f"_force_window_foreground error: {e}")
        # Last resort: try clicking the center of the window
        try:
            import pyautogui

            cx, cy = best.left + best.width // 2, best.top + best.height // 2
            pyautogui.click(cx, cy)
            time.sleep(0.2)
        except Exception:
            pass
        return False


def _paste_text(text: str) -> None:
    """Paste text via clipboard to avoid IME interference."""
    try:
        import pyperclip

        old = pyperclip.paste()
        pyperclip.copy(text)

        from server.services.executor.clicker import press_keys

        press_keys("ctrl", "v")
        time.sleep(0.2)

        try:
            pyperclip.copy(old)
        except Exception:
            pass
    except ImportError:
        # Fallback: typewrite (won't work for Chinese)
        from server.services.executor.clicker import type_text

        type_text(text)
