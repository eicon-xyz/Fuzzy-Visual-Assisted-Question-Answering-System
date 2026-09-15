"""T6 clicker.py 单元测试——mock 键鼠库，覆盖 direct/autogui/mock 三条执行路径。

clicker 在模块 import 时探测 pydirectinput/pyautogui 决定 _USE_DIRECT/_HAS_PYAUTOGUI。
测试策略：直接 monkeypatch 模块级标志与库函数，不依赖真实键鼠。
"""
from __future__ import annotations

import time

import pytest

import server.services.executor.clicker as ck


@pytest.fixture(autouse=True)
def _fast_time(monkeypatch):
    """消除 sleep 耗时。"""
    monkeypatch.setattr(ck.time, "sleep", lambda s: None)


# ── _safe_bbox / _clamp_coord 纯函数 ────────────────────────────────────


def test_safe_bbox_normalizes():
    assert ck._safe_bbox([1.9, 2.1]) == (1, 2)
    assert ck._safe_bbox((5, 6)) == (5, 6)
    assert ck._safe_bbox(None) is None
    with pytest.raises(ValueError):
        ck._safe_bbox("oops")
    with pytest.raises(ValueError):
        ck._safe_bbox([1])


def test_clamp_coord_bounds():
    assert ck._clamp_coord(-100, -100) == (5, 5)
    assert ck._clamp_coord(99999, 99999) == (1915, 1075)
    assert ck._clamp_coord(100, 200) == (100, 200)
    # 自定义屏幕尺寸
    assert ck._clamp_coord(50, 50, screen_w=100, screen_h=100) == (50, 50)
    assert ck._clamp_coord(95, 95, screen_w=100, screen_h=100) == (95, 95)


# ── mock 模式（无库可用时的降级路径）────────────────────────────────────


def test_mock_mode_logs_and_succeeds(monkeypatch):
    monkeypatch.setattr(ck, "_USE_DIRECT", False)
    monkeypatch.setattr(ck, "_HAS_PYAUTOGUI", False)
    r = ck.click_at([10, 20])
    assert r["success"] is True and r["x"] == 10 and r["y"] == 20
    r2 = ck.double_click_at([1, 1])
    assert r2["clicks"] == 2
    r3 = ck.right_click_at([1, 1])
    assert r3["button"] == "right"
    r4 = ck.type_text("hello")
    assert r4["success"] and r4["length"] == 5
    r5 = ck.press_keys("ctrl", "c")
    assert r5["keys"] == "ctrl+c"
    r6 = ck.scroll_at([5, 5], amount=3)
    assert r6["success"] and r6["amount"] == 3


# ── pydirectinput 优先路径 ──────────────────────────────────────────────


def test_direct_path_click_and_type(monkeypatch):
    calls = []
    monkeypatch.setattr(ck, "_USE_DIRECT", True)
    monkeypatch.setattr(ck, "_HAS_PYAUTOGUI", True)
    monkeypatch.setattr(
        ck.pydirectinput, "moveTo",
        lambda x, y, duration=0.2: calls.append(("moveTo", x, y)),
    )
    monkeypatch.setattr(
        ck.pydirectinput, "click",
        lambda button="left": calls.append(("click", button)),
    )
    monkeypatch.setattr(
        ck.pydirectinput, "hotkey",
        lambda *keys: calls.append(("hotkey", keys)),
    )
    monkeypatch.setattr(
        ck.pydirectinput, "scroll", lambda amount: calls.append(("scroll", amount)),
    )
    # 点击：direct 用循环 click（不用 pyautogui 的 clicks 参数）
    r = ck.click_at([100, 200], clicks=2)
    assert r["success"] and r["clicks"] == 2
    assert ("moveTo", 100, 200) in calls
    assert calls.count(("click", "left")) == 2
    # 右键
    r = ck.right_click_at([1, 1])
    assert r["button"] == "right"
    # 组合键
    r = ck.press_keys("ctrl", "v")
    assert ("hotkey", ("ctrl", "v")) in calls


def test_direct_path_type_via_clipboard(monkeypatch):
    """direct 路径 type_text：剪贴板 + keyDown/keyUp ctrl+v。"""
    calls = []
    monkeypatch.setattr(ck, "_USE_DIRECT", True)
    monkeypatch.setattr(ck, "_HAS_PYAUTOGUI", True)
    pdi = ck.pydirectinput
    monkeypatch.setattr(pdi, "keyDown", lambda k: calls.append(("keyDown", k)))
    monkeypatch.setattr(pdi, "keyUp", lambda k: calls.append(("keyUp", k)))
    import pyperclip

    monkeypatch.setattr(pyperclip, "paste", lambda: "old")
    copied = []
    monkeypatch.setattr(pyperclip, "copy", lambda t: copied.append(t))
    r = ck.type_text("中文内容")
    assert r["success"] and r["length"] == 4
    assert copied[0] == "中文内容"
    assert ("keyDown", "ctrl") in calls and ("keyDown", "v") in calls
    assert ("keyUp", "v") in calls and ("keyUp", "ctrl") in calls
    # 剪贴板被还原
    assert copied[-1] == "old"


def test_direct_path_hotkey_fallback(monkeypatch):
    """press_keys：无 hotkey 时逐个 keyDown/keyUp。"""
    calls = []
    monkeypatch.setattr(ck, "_USE_DIRECT", True)
    monkeypatch.setattr(ck, "_HAS_PYAUTOGUI", True)
    pdi = ck.pydirectinput
    monkeypatch.setattr(pdi, "hotkey", _no_attr)
    monkeypatch.setattr(pdi, "keyDown", lambda k: calls.append(("down", k)))
    monkeypatch.setattr(pdi, "keyUp", lambda k: calls.append(("up", k)))
    r = ck.press_keys("a", "b")
    assert r["success"]
    assert ("down", "a") in calls and ("down", "b") in calls
    assert ("up", "b") in calls and ("up", "a") in calls


def _no_attr(*a, **k):
    raise AttributeError("no hotkey")


def test_direct_drag(monkeypatch):
    calls = []
    monkeypatch.setattr(ck, "_USE_DIRECT", True)
    monkeypatch.setattr(ck, "_HAS_PYAUTOGUI", True)
    pdi = ck.pydirectinput
    monkeypatch.setattr(pdi, "mouseDown", lambda: calls.append("down"))
    monkeypatch.setattr(pdi, "mouseUp", lambda: calls.append("up"))
    monkeypatch.setattr(pdi, "moveTo", lambda x, y, duration=0.2: calls.append(("mv", x, y)))
    r = ck.execute_action("drag", None, [1, 2, 3, 4])
    assert r["success"] and r["drag"] == [1, 2, 3, 4]
    assert calls == ["down", ("mv", 3, 4), "up"] or ("mv", 3, 4) in calls
    # 非法 drag 参数
    r2 = ck.execute_action("drag", None, [1, 2])
    assert r2["success"] is False and "Invalid drag" in r2["error"]


# ── pyautogui 回退路径 ───────────────────────────────────────────────────


def test_autogui_path(monkeypatch):
    calls = []
    monkeypatch.setattr(ck, "_USE_DIRECT", False)
    monkeypatch.setattr(ck, "_HAS_PYAUTOGUI", True)
    monkeypatch.setattr(ck.pyautogui, "moveTo", lambda x, y, duration=0.2: calls.append("mv"))
    monkeypatch.setattr(ck.pyautogui, "click", lambda **k: calls.append("clk"))
    monkeypatch.setattr(ck.pyautogui, "hotkey", lambda *k: calls.append("hot"))
    monkeypatch.setattr(ck.pyautogui, "scroll", lambda a, **k: calls.append("scr"))
    r = ck.click_at([10, 10])
    assert r["success"]
    r = ck.press_keys("win")
    assert r["success"] and "hot" in calls


def test_autogui_scroll_at_position(monkeypatch):
    calls = []
    monkeypatch.setattr(ck, "_USE_DIRECT", False)
    monkeypatch.setattr(ck, "_HAS_PYAUTOGUI", True)
    monkeypatch.setattr(ck.pyautogui, "moveTo", lambda x, y, duration=0.1: None)
    monkeypatch.setattr(
        ck.pyautogui, "scroll", lambda amount, x=None, y=None: calls.append((amount, x, y))
    )
    r = ck.scroll_at([50, 60], amount=-5)
    assert r["success"] and r["amount"] == -5
    assert calls == [(-5, 50, 60)]


# ── execute_action 分发 ──────────────────────────────────────────────────


def test_execute_action_dispatch(monkeypatch):
    monkeypatch.setattr(ck, "_USE_DIRECT", False)
    monkeypatch.setattr(ck, "_HAS_PYAUTOGUI", False)
    assert ck.execute_action("click", [1, 2])["success"]
    assert ck.execute_action("double_click", [1, 2])["clicks"] == 2
    assert ck.execute_action("double_click", None)["keys"] == "win+r"
    assert ck.execute_action("right_click", [1, 2])["button"] == "right"
    assert ck.execute_action("type", None, "abc")["length"] == 3
    assert ck.execute_action("press_key", None, "ctrl+shift+s")["keys"] == "ctrl+shift+s"
    assert ck.execute_action("scroll", [1, 1], 2)["amount"] == 2
    assert ck.execute_action("move", [1, 1])["success"]
    r = ck.execute_action("wait", None, 0.01)
    assert r["success"] and r["waited"] == 0.01
    r = ck.execute_action("wait", None, {"seconds": 0.5})
    assert r["waited"] == 0.5
    r = ck.execute_action("launch_app", None, "calc")
    assert r["launched"] == "calc"
    r = ck.execute_action("nope", None)
    assert r["success"] is False and "Unknown action" in r["error"]


def test_click_none_bbox_keyboard_fallback(monkeypatch):
    monkeypatch.setattr(ck, "_USE_DIRECT", False)
    monkeypatch.setattr(ck, "_HAS_PYAUTOGUI", False)
    r = ck.click_at(None)
    assert r["success"] and "no coords" in r["msg"]
