"""
HAJIMI 自动操作助手 — 键鼠操作封装

基于 pyautogui + pydirectinput，纯坐标模拟执行。
UIA 精确操控将在后续版本实现。
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# pydirectinput 在 Windows 上更快更可靠（不抢焦点），回退 pyautogui
try:
    import pydirectinput

    _USE_DIRECT = True
    pydirectinput.FAILSAFE = False
except ImportError:
    _USE_DIRECT = False

try:
    import pyautogui

    _HAS_PYAUTOGUI = True
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
except ImportError:
    _HAS_PYAUTOGUI = False

if not _HAS_PYAUTOGUI and not _USE_DIRECT:
    logger.warning(
        "Neither pydirectinput nor pyautogui available — clicker in mock mode"
    )


def _safe_bbox(bbox_center):
    """确保坐标是整数二元组。None 时返回 None"""
    if bbox_center is None:
        return None
    if isinstance(bbox_center, (list, tuple)) and len(bbox_center) >= 2:
        return int(bbox_center[0]), int(bbox_center[1])
    raise ValueError(f"Invalid bbox_center: {bbox_center}")


def _clamp_coord(
    x: int, y: int, screen_w: int = 1920, screen_h: int = 1080, margin: int = 5
) -> tuple[int, int]:
    """裁剪坐标到屏幕边界内。"""
    x = max(margin, min(screen_w - margin, x))
    y = max(margin, min(screen_h - margin, y))
    return x, y


def _move_to(x: int, y: int, duration: float = 0.2):
    """平滑移动鼠标到目标坐标。"""
    x, y = _clamp_coord(x, y)
    if _USE_DIRECT:
        pydirectinput.moveTo(x, y, duration=duration)
    elif _HAS_PYAUTOGUI:
        pyautogui.moveTo(x, y, duration=duration)
    else:
        logger.info(f"mock move: ({x},{y})")


def _click(button: str = "left", clicks: int = 1):
    """点击鼠标。"""
    if _USE_DIRECT:
        for _ in range(clicks):
            pydirectinput.click(button=button)
            time.sleep(0.1)
    elif _HAS_PYAUTOGUI:
        pyautogui.click(button=button, clicks=clicks)
    else:
        logger.info(f"mock click: {button} x{clicks}")


# ═══════════════════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════════════════


def click_at(bbox_center, button: str = "left", clicks: int = 1) -> dict:
    """
    在指定坐标处点击。

    Args:
        bbox_center: [x, y] 或 (x, y) 坐标
        button: 'left' | 'right' | 'middle'
        clicks: 点击次数（1=单击, 2=双击）

    Returns:
        {"success": True, "x": int, "y": int, "button": str, "clicks": int}
    """
    if bbox_center is None:
        return {"success": True, "msg": "no coords, using keyboard shortcut"}
    x, y = _safe_bbox(bbox_center)
    x, y = _clamp_coord(x, y)
    _move_to(x, y, duration=0.2)
    time.sleep(0.15)
    _click(button=button, clicks=clicks)
    logger.info(f"click: ({x},{y}) {button} x{clicks}")
    return {"success": True, "x": x, "y": y, "button": button, "clicks": clicks}


def double_click_at(bbox_center) -> dict:
    """双击指定坐标。"""
    return click_at(bbox_center, clicks=2)


def right_click_at(bbox_center) -> dict:
    """右键点击指定坐标。"""
    return click_at(bbox_center, button="right")


def type_text(text: str, interval: float = 0.03) -> dict:
    if not text:
        return {"success": True, "text": "", "length": 0}
    if not _HAS_PYAUTOGUI and not _USE_DIRECT:
        logger.info(f"mock type: {text[:30]}")
        return {"success": True, "text": text, "length": len(text)}
    try:
        import pyperclip

        old = pyperclip.paste()
        pyperclip.copy(text)
        # 用 keyDown/keyUp 模拟 Ctrl+V（避免 hotkey bug）
        if _USE_DIRECT:
            import pydirectinput as pdi

            pdi.keyDown("ctrl")
            time.sleep(0.05)
            pdi.keyDown("v")
            time.sleep(0.1)
            pdi.keyUp("v")
            pdi.keyUp("ctrl")
        else:
            press_keys("ctrl", "v")
        time.sleep(0.3)
        try:
            pyperclip.copy(old)
        except Exception:
            pass
    except ImportError:
        if _USE_DIRECT:
            import pydirectinput as pdi

            pdi.typewrite(text, interval=interval)
        else:
            pyautogui.typewrite(text, interval=interval)
    logger.info(f"type: {len(text)} chars")
    return {"success": True, "text": text, "length": len(text)}


def press_keys(*keys: str) -> dict:
    key_str = "+".join(keys)
    if _USE_DIRECT:
        try:
            pydirectinput.hotkey(*keys)
        except AttributeError:
            # 某些版本无 hotkey，逐个按
            import pydirectinput as pdi

            for k in keys:
                pdi.keyDown(k)
            for k in reversed(keys):
                pdi.keyUp(k)
    elif _HAS_PYAUTOGUI:
        pyautogui.hotkey(*keys)
    else:
        logger.info(f"mock press_keys: {key_str}")
    return {"success": True, "keys": key_str}


def scroll_at(bbox_center, amount: int = -3) -> dict:
    x, y = _safe_bbox(bbox_center)
    x, y = _clamp_coord(x, y)
    _move_to(x, y, duration=0.1)
    time.sleep(0.1)
    if _USE_DIRECT:
        pydirectinput.scroll(amount)
    elif _HAS_PYAUTOGUI:
        pyautogui.scroll(amount, x=x, y=y)
    else:
        logger.info(f"mock scroll: ({x},{y}) amount={amount}")
    return {"success": True, "x": x, "y": y, "amount": amount}


def move_to(bbox_center) -> dict:
    """移动鼠标到指定坐标（不点击）。"""
    x, y = _safe_bbox(bbox_center)
    x, y = _clamp_coord(x, y)
    _move_to(x, y, duration=0.3)
    return {"success": True, "x": x, "y": y}


def execute_action(action: str, bbox_center, params=None) -> dict:
    """
    根据 action 类型执行对应的操作。

    Args:
        action: 'click'|'double_click'|'right_click'|'type'|'press_key'|'scroll'|'wait'|'move'
        bbox_center: [x, y] 坐标（type/press_key/wait 时可为 None）
        params: action 参数

    Returns:
        操作结果 dict，包含 success 字段
    """
    if action == "click":
        return click_at(bbox_center)
    elif action in ("double_click", "locate_icon", "find_icon"):
        return double_click_at(bbox_center) if bbox_center else press_keys("win", "r")
    elif action == "right_click":
        return right_click_at(bbox_center)
    elif action == "type":
        return type_text(str(params or ""))
    elif action == "press_key":
        keys = str(params or "enter").split("+")
        return press_keys(*keys)
    elif action == "scroll":
        return scroll_at(bbox_center, int(params or -3))
    elif action == "wait":
        # params: seconds or {seconds: N} or {x, y} (ignore coords in wait)
        if isinstance(params, dict):
            secs = float(params.get("seconds", params.get("secs", 1.0)))
        else:
            secs = float(params or 1.0)
        time.sleep(secs)
        return {"success": True, "waited": secs}
    elif action == "move":
        return move_to(bbox_center)
    elif action == "drag":
        if params and len(params) == 4:
            x1, y1, x2, y2 = map(int, params)
            _move_to(x1, y1, duration=0.2)
            if _USE_DIRECT:
                pydirectinput.mouseDown()
                pydirectinput.moveTo(x2, y2, duration=0.5)
                pydirectinput.mouseUp()
            elif _HAS_PYAUTOGUI:
                pyautogui.drag(x2 - x1, y2 - y1, duration=0.5)
            else:
                logger.info(f"mock drag: ({x1},{y1})->({x2},{y2})")
            return {"success": True, "drag": params}
        return {"success": False, "error": f"Invalid drag params: {params}"}
    elif action == "launch_app":
        logger.info(f"launch_app step (no-op in engine): {params}")
        return {"success": True, "launched": str(params or "unknown")}
    else:
        return {"success": False, "error": f"Unknown action: {action}"}
