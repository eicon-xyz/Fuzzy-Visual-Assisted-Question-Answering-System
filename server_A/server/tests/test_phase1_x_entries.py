"""Phase 1 边界验收：五条降级边界在**无许可**时必须拒绝，且不得碰到输入/像素。

这组测试对应设计稿 §2 的边界表：
    click  → 坐标/双击/右键       (uia_bridge._act_coord)
    type   → SetFocus+剪贴板       (uia_bridge._act_type 降级分支)
    activate → SetFocus            (uia_bridge.act_window)
    launch → Win+搜索              (launcher._launch_win_search)
    observe → 整屏抓取             (screen_capture.capture_fullscreen)

判据统一为：error_code == permit_required，且底层设备调用计数 == 0。
"""

from __future__ import annotations

import pytest

from server.services.executor import hid
from server.services.executor.permit import (
    ForegroundAction,
    PermitBroker,
    TaskPolicy,
)
from server.services.executor.screen_capture import CaptureFailure, capture_fullscreen
from server.services.executor.uia_bridge import UIABridge


class _Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class _FakeControl:
    """够 _control_bbox / SetFocus / GetTopLevelControl 用的最小控件。"""

    def __init__(self, name="记事本", ctype="WindowControl", rect=(100, 100, 500, 400)):
        self.Name = name
        self.ControlTypeName = ctype
        self.BoundingRectangle = _Rect(*rect)
        self.IsEnabled = True
        self.IsOffscreen = False
        self.log: list[str] = []

    def GetTopLevelControl(self):
        return self

    def SetFocus(self):
        self.log.append("setfocus")

    def GetChildren(self):
        return []


def _spy_hid(monkeypatch) -> list:
    """装上 hid 设备层探针：任何真实键鼠调用都会落进返回的列表。"""
    calls: list[tuple] = []
    monkeypatch.setattr(hid, "_move_raw", lambda x, y, duration=0.2: calls.append(("move", x, y)))
    monkeypatch.setattr(hid, "_click_raw", lambda button="left", clicks=1: calls.append(("click", button, clicks)))
    monkeypatch.setattr(hid, "_hotkey_raw", lambda *k: calls.append(("hotkey", k)))
    return calls


@pytest.fixture
def bridge():
    b = UIABridge()  # permit=None ← 默认 fail-closed
    b._available = True
    return b


def _permit(actions):
    broker = PermitBroker()
    return broker.resolve(
        TaskPolicy(task_id="t", actions=frozenset(actions)), consent=True
    )


# ── 边界 1：坐标点击 ────────────────────────────────────────────────────────


def test_boundary_click_refused_without_permit(bridge, monkeypatch):
    calls = _spy_hid(monkeypatch)
    ctrl = _FakeControl()
    r = bridge._act_coord(ctrl, "e1")
    assert r["success"] is False
    assert r["error_code"] == "permit_required"
    assert calls == [], "拒绝时绝不能动光标"


def test_boundary_click_allowed_with_permit(bridge, monkeypatch):
    calls = _spy_hid(monkeypatch)
    bridge._permit = _permit({ForegroundAction.POINTER})
    r = bridge._act_coord(_FakeControl(), "e1")
    assert r["success"] is True
    assert r["via"] == "coord"
    assert calls == [("move", 300, 250), ("click", "left", 1)]


def test_boundary_double_and_right_click_are_gated(bridge, monkeypatch):
    calls = _spy_hid(monkeypatch)
    """double_click / right_click 无条件走 _act_coord —— 也必须被拦。"""
    for _action in ("double_click", "right_click"):
        assert bridge._act_coord(_FakeControl(), "e1")["error_code"] == "permit_required"
    assert calls == []


# ── 边界 2：type 的焦点+剪贴板降级 ─────────────────────────────────────────


def test_boundary_type_fallback_refused_without_permit(bridge):
    ctrl = _FakeControl("输入框", "EditControl")
    bridge._last_meta["e1"] = {"patterns": []}  # 无 value pattern → 走降级
    r = bridge._act_type(ctrl, "e1", "你好")
    assert r["success"] is False
    assert r["error_code"] == "permit_required"
    assert ctrl.log == [], "无许可时不得 SetFocus"


def test_boundary_type_fallback_needs_three_scopes(bridge):
    ctrl = _FakeControl("输入框", "EditControl")
    bridge._last_meta["e1"] = {"patterns": []}
    bridge._permit = _permit({ForegroundAction.ACTIVATE})  # 缺 clipboard/keyboard
    r = bridge._act_type(ctrl, "e1", "你好")
    assert r["error_code"] == "permit_required"
    assert set(r["required_actions"]) == {"activate", "clipboard", "keyboard"}
    assert ctrl.log == []


# ── 边界 3：窗口 activate ──────────────────────────────────────────────────


def test_boundary_activate_refused_without_permit(bridge):
    ctrl = _FakeControl()
    bridge._handles["eWin"] = ctrl
    r = bridge.act_window("activate", element_id="eWin")
    assert r["success"] is False
    assert r["error_code"] == "permit_required"
    assert ctrl.log == [], "无许可时不得 SetFocus"


# ── 边界 4：launch 第 3 层 Win+搜索 ────────────────────────────────────────


def test_boundary_launch_layer3_refused_without_permit(monkeypatch):
    calls = _spy_hid(monkeypatch)
    from server.services.launcher import _launch_win_search

    r = _launch_win_search("某不存在的应用", permit=None)
    assert r["ok"] is False
    assert r["error_code"] == "permit_required"
    assert calls == []
    assert "第 1/2 层" in r["hint"]


def test_launch_app_surfaces_refusal(monkeypatch):
    import server.services.launcher as launcher

    monkeypatch.setattr(launcher, "_resolve_executable", lambda name: None)
    out = launcher.launch_app("某不存在的应用", permit=None)
    assert out["success"] is False
    assert out["error_code"] == "permit_required"
    assert out["tier"] == 3


# ── 边界 5：整屏抓取 ──────────────────────────────────────────────────────


def test_boundary_fullscreen_capture_refused_without_permit():
    f = capture_fullscreen(None, (0, 0, 100, 100))
    assert f.available is False
    assert f.failure == CaptureFailure.NO_PERMIT


# ── agent 工具层的三个直连入口 ────────────────────────────────────────────


def test_agent_press_key_refused(monkeypatch):
    calls = _spy_hid(monkeypatch)
    from server.services.executor.agent import ExecutionAgent

    a = ExecutionAgent()  # permit=None
    r = a._do_press_key("ctrl+s")
    assert r["success"] is False
    assert r["error_code"] == "permit_required"
    assert calls == []


def test_agent_paste_refused(monkeypatch):
    calls = _spy_hid(monkeypatch)
    from server.services.executor.agent import ExecutionAgent

    a = ExecutionAgent()
    r = a._do_paste_text("hello")
    assert r["success"] is False
    assert r["error_code"] == "permit_required"
    assert calls == []


def test_agent_scroll_refused(monkeypatch):
    calls = _spy_hid(monkeypatch)
    from server.services.executor.agent import ExecutionAgent

    a = ExecutionAgent()
    r = a._do_scroll("down", 3)
    assert r["success"] is False
    assert r["error_code"] == "permit_required"
