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


def _launch_win_search(app_name: str, permit=None) -> dict:
    """Layer 3 fallback: Win+Search keyboard simulation.

    Opens Start Menu, pastes the app name, presses Enter.
    Less reliable (especially in RDP sessions) but works for UWP apps
    and custom-installed apps not on PATH.

    Phase 1：这是 launch_app 的**降级边界**（会开开始菜单、写剪贴板、向前台发键），
    所以整个函数要 KEYBOARD+CLIPBOARD+ACTIVATE 许可。无许可时返回拒绝，由
    调用方决定是否改走 mark_step_failed——绝不静默降级。
    """
    from server.services.executor.hid import paste as hid_paste
    from server.services.executor.hid import precheck, press_key
    from server.services.executor.permit import ForegroundAction

    required = (
        ForegroundAction.KEYBOARD,
        ForegroundAction.CLIPBOARD,
        ForegroundAction.ACTIVATE,
    )
    denied = precheck(permit, required, "launcher.win_search")
    if denied is not None:
        return {
            "ok": False,
            "tier": 3,
            **denied,
            "hint": (
                "启动应用的第 1/2 层（映射表/PATH）都没命中，第 3 层要模拟 Win+搜索按键，"
                "需要接管许可。改用别的办法启动该应用，或调用 mark_step_failed 说明"
                "需要用户手动打开。"
            ),
        }

    # 1. Open Start Menu（Win 键必须 keyDown/keyUp，hotkey 在 Win11 上不可靠）
    r = press_key(permit, "win", hold_ms=200)
    if not r.ok:
        return {"ok": False, "tier": 3, **r.to_dict()}
    time.sleep(0.5)

    # 2. Paste search query via clipboard (bypasses IME)
    r = hid_paste(permit, app_name)
    if not r.ok:
        return {"ok": False, "tier": 3, **r.to_dict()}
    time.sleep(0.8)

    # 3. Press Enter to select the first search result
    r = press_key(permit, "enter", hold_ms=80)
    if not r.ok:
        return {"ok": False, "tier": 3, **r.to_dict()}
    time.sleep(0.5)

    # 4. Close Start Menu in case Enter didn't work
    press_key(permit, "esc", hold_ms=60)
    time.sleep(0.2)

    logger.info(f"Layer 3 (Win+Search): launched '{app_name}'")
    return {"ok": True, "tier": 3, "method": "win_search"}


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


def launch_app(app_name: str, permit=None) -> dict:
    """Launch an application using the 3-tier fallback strategy.

    Tier 1: Mapping table → subprocess/os.startfile (100% reliable)
    Tier 2: shutil.which() PATH lookup → subprocess (90%+ reliable)
    Tier 3: Win+Search keyboard simulation (fallback, ~80% reliable)

    Phase 1：层 1/2 走 subprocess，不碰桌面，**不需要接管许可**；层 3 是
    Win+搜索键盘模拟，属降级边界，需要 KEYBOARD+CLIPBOARD+ACTIVATE。
    提前台是可选优化：无 ACTIVATE 许可时跳过，不影响"启动成功"这个结论。

    Args:
        app_name: The application name (Chinese or English, e.g. "记事本", "Chrome").
        permit: 接管许可（Phase 1）。None = 只能用层 1/2。

    Returns:
        {"success": True, "app_name": str, "method": "direct"|"win_search",
         "tier": int, "foreground": "ok"|"skipped(no permit)"|...}
        or {"success": False, "app_name": str, "error": str, "error_code"?: str}
    """
    if not app_name:
        return {
            "success": False,
            "app_name": app_name or "",
            "error": "empty app name",
        }

    logger.info("Launching '%s' (3-tier strategy)", app_name)

    def _fg_state(app: str) -> str:
        fg = _force_window_foreground(app, permit=permit)
        if fg["ok"]:
            return "ok"
        return "skipped(no permit)" if fg["skipped"] else fg["reason"]

    # ── Tier 1 + 2: Direct launch via mapping or PATH（不碰桌面，无需许可）──
    executable = _resolve_executable(app_name)
    if executable:
        success = _launch_direct(executable)
        if success:
            time.sleep(3)  # Wait for app to render
            return {
                "success": True,
                "app_name": app_name,
                "method": "direct",
                "tier": 1 if executable in APP_EXECUTABLE_MAP.values() else 2,
                "executable": executable,
                "foreground": _fg_state(app_name),
            }
        logger.warning(
            "Direct launch returned but process may not have started; "
            "falling through to Win+Search"
        )

    # ── Tier 3: Win+Search fallback（降级边界，要许可）──
    r3 = _launch_win_search(app_name, permit=permit)
    if r3.get("ok"):
        time.sleep(3)
        return {
            "success": True,
            "app_name": app_name,
            "method": "win_search",
            "tier": 3,
            "foreground": _fg_state(app_name),
        }

    out = {
        "success": False,
        "app_name": app_name,
        "error": r3.get("error") or "all 3 launch tiers failed",
        "tier": 3,
    }
    for k in ("error_code", "hint", "required_actions"):
        if r3.get(k) is not None:
            out[k] = r3[k]
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Window foreground helper
# ═══════════════════════════════════════════════════════════════════════════


def _force_window_foreground(app_name: str, permit=None) -> dict:
    """把应用窗口提到前台。

    Phase 1：提前台 = ACTIVATE，属 X 档。但它是**可选优化**——应用已经启动成功，
    提前台失败不该让整个 launch 失败。所以无许可时返回 skipped 而不是报错。

    Returns: {"ok": bool, "skipped": bool, "reason": str}
    """
    from server.services.executor.hid import activate_window, precheck
    from server.services.executor.permit import ForegroundAction

    denied = precheck(permit, (ForegroundAction.ACTIVATE,), "launcher.foreground")
    if denied is not None:
        return {"ok": False, "skipped": True, "reason": "permit_required"}

    time.sleep(0.5)
    r = activate_window(permit, app_name)
    if not r.ok:
        logger.warning("_force_window_foreground: %s", r.error)
        return {"ok": False, "skipped": False, "reason": r.error_code or "failed"}
    return {"ok": True, "skipped": False, "reason": "ok"}


def _paste_text(text: str, permit=None) -> dict:
    """Paste text via clipboard to avoid IME interference.

    Phase 1：写全局剪贴板 + 向当前焦点发 ctrl+v，走 hid（CLIPBOARD+KEYBOARD）。
    """
    from server.services.executor.hid import paste as hid_paste

    return hid_paste(permit, text).to_dict()
