"""采集前台窗口、进程与场景提示，fail-open。"""
from __future__ import annotations

import platform
import sys
from typing import Any, Dict, List, Optional


def _infer_scene_hint(title: str, process_name: str, class_name: str) -> str:
    t = (title or "").lower()
    p = (process_name or "").lower()
    c = (class_name or "").lower()
    if "explorer" in p or t in ("", "program manager", "桌面"):
        return "desktop"
    if any(k in p for k in ("chrome", "msedge", "firefox", "brave")):
        return "browser"
    if any(k in t for k in ("wps", "金山", "word", "excel", "et", "wpp")) or "wps" in p:
        return "wps"
    if "explorer" in p and ("desktop" in c or "progman" in c or "workerw" in c):
        return "desktop"
    return "unknown"


def _gather_foreground_windows() -> Dict[str, Any]:
    if platform.system() != "Windows":
        return {}
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {}

        length = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buf, length)
        title = buf.value or ""

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = ""
        try:
            import psutil

            process_name = psutil.Process(pid.value).name()
        except Exception:
            pass

        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buf, 256)
        class_name = class_buf.value or ""

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        window_rect = [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)]

        return {
            "window_title": title,
            "process_name": process_name,
            "class_name": class_name,
            "rect": window_rect,
            "hwnd": int(hwnd),
        }
    except Exception as exc:
        print(f"[assist_collect] foreground failed: {exc}", file=sys.stderr)
        return {}


def _gather_local_desktop_shortcuts() -> List[Dict[str, Any]]:
    if platform.system() != "Windows":
        return []
    try:
        from pathlib import Path

        desktop = Path.home() / "Desktop"
        if not desktop.is_dir():
            return []
        out: List[Dict[str, Any]] = []
        for lnk in desktop.glob("*.lnk"):
            name = lnk.stem
            if name:
                out.append({"name": name, "source": "desktop_shortcut", "path": str(lnk)})
        return out[:40]
    except Exception:
        return []


def gather_assist_bundle() -> dict:
    """构建 AssistBundle；任何子步骤失败均返回部分数据。"""
    fg = _gather_foreground_windows()
    title = fg.get("window_title") or ""
    process_name = fg.get("process_name") or ""
    class_name = fg.get("class_name") or ""
    scene = _infer_scene_hint(title, process_name, class_name)
    shortcuts = _gather_local_desktop_shortcuts() if scene == "desktop" else []

    return {
        "foreground": fg,
        "screen": {"scene_hint": scene},
        "local_candidates": shortcuts,
    }


def foreground_window_title(bundle: Optional[dict] = None) -> str:
    if bundle:
        fg = bundle.get("foreground") or {}
        title = fg.get("window_title") or ""
        if title:
            return title
    gathered = gather_assist_bundle()
    return (gathered.get("foreground") or {}).get("window_title") or "桌面"
