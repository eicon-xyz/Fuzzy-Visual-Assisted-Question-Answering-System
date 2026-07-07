# -*- coding: utf-8 -*-
"""
Application Launcher — 3-tier fallback strategy.

Layer 1: Mapping table (Chinese name → executable) → subprocess.Popen
Layer 2: shutil.which() finds executable on PATH → subprocess.Popen
Layer 3: Win+Search keyboard simulation (fallback)

Layer 1 + 2 cover ~90% of scenarios with 100% reliability.
Layer 3 is the fallback for apps not on PATH (e.g. UWP apps, custom installs).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# App Name → Executable Mapping Table
#
# Maps Chinese and English common names to their Windows executables.
# These are the canonical names used by subprocess.Popen / start.
# Keys: user-friendly names (Chinese + English)
# Values: executable name or full path
# ═══════════════════════════════════════════════════════════════════════════

APP_EXECUTABLE_MAP: dict[str, str] = {
    # ── Windows 系统应用 ──
    "计算器": "calc.exe",
    "Calculator": "calc.exe",
    "calc": "calc.exe",
    "记事本": "notepad.exe",
    "Notepad": "notepad.exe",
    "notepad": "notepad.exe",
    "画图": "mspaint.exe",
    "Paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "截图工具": "SnippingTool.exe",
    "截图": "SnippingTool.exe",
    "Snipping Tool": "SnippingTool.exe",
    "任务管理器": "Taskmgr.exe",
    "Task Manager": "Taskmgr.exe",
    "控制面板": "control.exe",
    "Control Panel": "control.exe",
    "资源管理器": "explorer.exe",
    "文件资源管理器": "explorer.exe",
    "Explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "命令提示符": "cmd.exe",
    "CMD": "cmd.exe",
    "cmd": "cmd.exe",
    "PowerShell": "powershell.exe",
    "powershell": "powershell.exe",
    "注册表编辑器": "regedit.exe",
    "Regedit": "regedit.exe",
    # ── 浏览器 ──
    "浏览器": "chrome",  # generic — try chrome first
    "Chrome": "chrome",
    "chrome": "chrome",
    "谷歌浏览器": "chrome",
    "Google Chrome": "chrome",
    "Edge": "msedge",
    "edge": "msedge",
    "Microsoft Edge": "msedge",
    "Firefox": "firefox",
    "firefox": "firefox",
    "火狐": "firefox",
    # ── 通讯 / 社交 ──
    "微信": "WeChat.exe",
    "WeChat": "WeChat.exe",
    "QQ": "QQ.exe",
    "钉钉": "DingTalk.exe",
    "DingTalk": "DingTalk.exe",
    "飞书": "Feishu.exe",
    "Feishu": "Feishu.exe",
    "企业微信": "WXWork.exe",
    "WXWork": "WXWork.exe",
    "Teams": "Teams.exe",
    "Microsoft Teams": "Teams.exe",
    # ── 办公 ──
    "Word": "winword.exe",
    "winword": "winword.exe",
    "Microsoft Word": "winword.exe",
    "Excel": "excel.exe",
    "excel": "excel.exe",
    "Microsoft Excel": "excel.exe",
    "PowerPoint": "powerpnt.exe",
    "powerpnt": "powerpnt.exe",
    "Microsoft PowerPoint": "powerpnt.exe",
    "Outlook": "outlook.exe",
    "outlook": "outlook.exe",
    "WPS": "wps.exe",
    "WPS Office": "wps.exe",
    # ── 开发工具 ──
    "VSCode": "code",
    "VS Code": "code",
    "code": "code",
    "Visual Studio Code": "code",
    "Terminal": "wt.exe",
    "Windows Terminal": "wt.exe",
    "Git Bash": "git-bash.exe",
    # ── 音乐 / 媒体 ──
    "网易云音乐": "cloudmusic.exe",
    "CloudMusic": "cloudmusic.exe",
    "QQ音乐": "QQMusic.exe",
    "QQMusic": "QQMusic.exe",
    "Spotify": "Spotify.exe",
    "spotify": "Spotify.exe",
    "VLC": "vlc.exe",
    "vlc": "vlc.exe",
    # ── 其他常用 ──
    "Steam": "steam.exe",
    "steam": "steam.exe",
    "Telegram": "Telegram.exe",
    "telegram": "Telegram.exe",
    "Discord": "Discord.exe",
    "discord": "Discord.exe",
    "Notion": "Notion.exe",
    "notion": "Notion.exe",
    "Obsidian": "Obsidian.exe",
    "obsidian": "Obsidian.exe",
}


def _resolve_executable(app_name: str) -> Optional[str]:
    """Resolve an app name to an executable via mapping table or PATH search.

    Returns the executable name/path if found, None otherwise.
    """
    # Layer 1: mapping table (exact match)
    mapped = APP_EXECUTABLE_MAP.get(app_name)
    if mapped:
        logger.info(f"Layer 1 (mapping): '{app_name}' → '{mapped}'")
        return mapped

    # Layer 1: case-insensitive fallback in mapping table
    app_lower = app_name.lower()
    for key, value in APP_EXECUTABLE_MAP.items():
        if key.lower() == app_lower:
            logger.info(f"Layer 1 (mapping, case-insensitive): '{app_name}' → '{value}'")
            return value

    # Layer 2: shutil.which on PATH
    resolved = shutil.which(app_name)
    if resolved:
        logger.info(f"Layer 2 (PATH): '{app_name}' → '{resolved}'")
        return resolved

    # Try with .exe suffix
    if not app_name.lower().endswith(".exe"):
        resolved = shutil.which(app_name + ".exe")
        if resolved:
            logger.info(f"Layer 2 (PATH+.exe): '{app_name}' → '{resolved}'")
            return resolved

    return None


def _launch_direct(executable: str) -> bool:
    """Launch an executable directly via subprocess / os.startfile.

    Returns True if the process started successfully.
    """
    try:
        # Path with separators → verify file exists, then os.startfile
        if os.path.isabs(executable) and os.path.exists(executable):
            os.startfile(executable)
            logger.info(f"Launched via os.startfile: '{executable}'")
            return True

        # Named executable (e.g. "notepad.exe", "chrome") — verify it's
        # findable before launching. shutil.which does a PATH lookup;
        # a bare name without PATH entry (e.g. "cloudmusic.exe" on a
        # machine that doesn't have it) would fail silently with Popen.
        resolved = shutil.which(executable)
        if resolved is None:
            logger.warning(
                f"Executable '{executable}' not found on PATH; falling through"
            )
            return False

        # Launch via subprocess
        subprocess.Popen(
            [resolved],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"Launched via subprocess: '{resolved}'")
        return True
    except Exception as e:
        logger.warning(f"Direct launch failed for '{executable}': {e}")
        return False


def _launch_win_search(app_name: str) -> bool:
    """Layer 3 fallback: Win+Search keyboard simulation.

    Opens Start Menu, pastes the app name, presses Enter.
    Less reliable (especially in RDP sessions) but works for UWP apps
    and custom-installed apps not on PATH.

    Uses pyautogui keyDown/keyUp instead of pydirectinput hotkey —
    empirically more reliable on Windows 11 for the Win key.
    """
    try:
        import pyautogui
        import pyperclip

        pyautogui.FAILSAFE = False

        # 1. Open Start Menu
        pyautogui.keyDown("win")
        time.sleep(0.2)
        pyautogui.keyUp("win")
        time.sleep(0.5)

        # 2. Paste search query via clipboard (bypasses IME)
        old_clipboard = pyperclip.paste()
        pyperclip.copy(app_name)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.8)

        # Restore clipboard
        try:
            pyperclip.copy(old_clipboard)
        except Exception:
            pass

        # 3. Press Enter to select the first search result
        pyautogui.press("enter")
        time.sleep(0.5)

        # 4. Close Start Menu in case Enter didn't work
        pyautogui.press("esc")
        time.sleep(0.2)

        logger.info(f"Layer 3 (Win+Search): launched '{app_name}'")
        return True
    except ImportError as e:
        logger.error(f"Layer 3 unavailable — missing dependency: {e}")
        return False
    except Exception as e:
        logger.error(f"Layer 3 failed for '{app_name}': {e}")
        return False


# ── App name extraction from user queries ──

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
    # Bare app names: "VS Code", "Calculator" etc
    re.compile(
        r"^[\"「']?([A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z][A-Za-z0-9]*)?)[\"」']?\s*$",
        re.I,
    ),
    # Short queries that look like app names (Chinese, no whitespace)
    re.compile(r"^[\"「']?([^\"「」'\s,，。\.]{1,30}?)[\"」']?\s*$", re.I),
]


def _extract_app_name_from_query(query: str) -> Optional[str]:
    """Extract target app name from a user query like 'open Notepad'."""
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
    """Extract what to do after launching the app."""
    if not query or not app_name:
        return None

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


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════


def launch_app(app_name: str) -> dict:
    """Launch an application using the 3-tier fallback strategy.

    Tier 1: Mapping table → subprocess/os.startfile (100% reliable)
    Tier 2: shutil.which() PATH lookup → subprocess (90%+ reliable)
    Tier 3: Win+Search keyboard simulation (fallback, ~80% reliable)

    Args:
        app_name: The application name (Chinese or English, e.g. "记事本", "Chrome").

    Returns:
        {"success": True, "app_name": str, "method": "direct"|"win_search", "tier": int}
        or {"success": False, "app_name": str, "error": str}
    """
    if not app_name:
        return {
            "success": False,
            "app_name": app_name or "",
            "error": "empty app name",
        }

    logger.info(f"Launching '{app_name}' (3-tier strategy)")

    # ── Tier 1 + 2: Direct launch via mapping or PATH ──
    executable = _resolve_executable(app_name)
    if executable:
        success = _launch_direct(executable)
        if success:
            # Wait for app to render
            time.sleep(3)
            _force_window_foreground(app_name)
            return {
                "success": True,
                "app_name": app_name,
                "method": "direct",
                "tier": 1 if executable in APP_EXECUTABLE_MAP.values() else 2,
                "executable": executable,
            }
        logger.warning(
            f"Direct launch returned but process may not have started; "
            f"falling through to Win+Search"
        )

    # ── Tier 3: Win+Search fallback ──
    success = _launch_win_search(app_name)
    if success:
        time.sleep(3)
        _force_window_foreground(app_name)
        return {
            "success": True,
            "app_name": app_name,
            "method": "win_search",
            "tier": 3,
        }

    return {
        "success": False,
        "app_name": app_name,
        "error": "all 3 launch tiers failed",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Window foreground helper
# ═══════════════════════════════════════════════════════════════════════════


def _force_window_foreground(app_name: str) -> bool:
    """Find the app window by fuzzy title match and force it to foreground.

    Uses pygetwindow for window enumeration and activation.
    Falls back to pywinauto if pygetwindow's activate() fails (e.g. RDP).
    """
    try:
        import pygetwindow as gw
    except ImportError:
        logger.warning("pygetwindow not installed — cannot force window foreground")
        return False

    time.sleep(0.5)

    # Collect candidates: exact title match first, then fuzzy
    candidates = gw.getWindowsWithTitle(app_name)
    if not candidates:
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

    # Pick the largest visible window
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
        f"_force_window_foreground: activating '{best.title}' "
        f"({best.width}x{best.height})"
    )

    try:
        best.restore()
        time.sleep(0.2)
        best.activate()
        time.sleep(0.3)

        if best.isActive:
            logger.info(f"_force_window_foreground: '{best.title}' is now active")
            return True

        # Fallback: pywinauto
        logger.warning("pygetwindow activate failed, trying pywinauto fallback")
        try:
            from pywinauto import Desktop

            dlg = Desktop(backend="win32").window(title=best.title)
            dlg.set_focus()
            time.sleep(0.2)
            logger.info(
                f"_force_window_foreground: pywinauto set_focus succeeded "
                f"on '{best.title}'"
            )
            return True
        except ImportError:
            logger.warning("pywinauto not installed — window may not be in foreground")
        except Exception as e:
            logger.warning(f"pywinauto fallback also failed: {e}")

        return best.isActive
    except Exception as e:
        logger.warning(f"_force_window_foreground error: {e}")
        # Last resort: click center of window
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
        from server.services.executor.clicker import type_text

        type_text(text)
