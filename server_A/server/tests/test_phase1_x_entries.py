"""Phase 1 边界验收：五条降级边界在**无许可**时必须拒绝，且不得碰到输入/像素。

这组测试对应设计稿 §2 的边界表：
    click  → 坐标/双击/右键       (uia_bridge._act_coord)
    type   → WM_CHAR 投递，再退到 SetFocus+剪贴板 (uia_bridge._act_type)
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

    def __init__(
        self, name="记事本", ctype="WindowControl", rect=(100, 100, 500, 400), hwnd=0
    ):
        self.Name = name
        self.ControlTypeName = ctype
        self.BoundingRectangle = _Rect(*rect)
        self.IsEnabled = True
        self.IsOffscreen = False
        self.NativeWindowHandle = hwnd
        self._top = None
        self.log: list[str] = []

    def GetTopLevelControl(self):
        return self._top or self

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


# ── 边界 2b：type 优先投递 WM_CHAR（W 档，不抢焦点、不改剪贴板）────────────


def _edit_with_own_hwnd():
    """输入框自身有 HWND，且与顶层窗口不同——WM_CHAR 可以定向投递。"""
    top = _FakeControl("窗口", "WindowControl", hwnd=0x9000)
    edit = _FakeControl("输入框", "EditControl", hwnd=0x1234)
    edit._top = top
    return edit


def test_type_prefers_message_over_clipboard(bridge, monkeypatch):
    ctrl = _edit_with_own_hwnd()
    bridge._last_meta["e1"] = {"patterns": []}  # 无 value pattern
    bridge._permit = _permit(set(ForegroundAction))
    calls: list[tuple] = []

    def fake_post_text(permit, hwnd, text):
        calls.append((hwnd, text))
        return hid.HIDResult(
            ok=True,
            actions=(ForegroundAction.WINDOW_MESSAGE,),
            detail={"via": "message", "posted": len(text)},
        )

    monkeypatch.setattr(hid, "post_text", fake_post_text)
    r = bridge._act_type(ctrl, "e1", "你好")
    assert r["success"] is True
    assert r["via"] == "message"
    assert calls == [(0x1234, "你好")], "必须投给控件自身的 HWND"
    assert ctrl.log == [], "W 档不得 SetFocus"


def test_type_message_partial_delivery_does_not_paste(bridge, monkeypatch):
    """已投递出去一部分再粘贴 = 重复输入，所以只能报失败。"""
    ctrl = _edit_with_own_hwnd()
    bridge._last_meta["e1"] = {"patterns": []}
    bridge._permit = _permit(set(ForegroundAction))
    monkeypatch.setattr(
        hid,
        "post_text",
        lambda *a, **k: hid.HIDResult(
            ok=False,
            actions=(ForegroundAction.WINDOW_MESSAGE,),
            error_code="path_unavailable",
            error="PostMessage(WM_CHAR) failed after 2 char(s)",
            detail={"posted": 2},
        ),
    )
    r = bridge._act_type(ctrl, "e1", "你好世界")
    assert r["success"] is False
    assert r["posted"] == 2
    assert ctrl.log == [], "未走粘贴，不得 SetFocus"


def test_type_falls_back_to_paste_when_nothing_posted(bridge, monkeypatch):
    """一个字都没投递（无 pywin32 / 句柄失效）→ 仍在动手之前，可走粘贴。"""
    ctrl = _edit_with_own_hwnd()
    bridge._last_meta["e1"] = {"patterns": []}
    bridge._permit = _permit(set(ForegroundAction))
    monkeypatch.setattr(
        hid,
        "post_text",
        lambda *a, **k: hid.HIDResult(
            ok=False,
            actions=(ForegroundAction.WINDOW_MESSAGE,),
            error_code="path_unavailable",
            error="win32gui unavailable or no hwnd",
            detail={"posted": 0},
        ),
    )
    monkeypatch.setattr(
        hid,
        "set_focus",
        lambda permit, control: hid.HIDResult(
            ok=True, actions=(ForegroundAction.ACTIVATE,)
        ),
    )
    monkeypatch.setattr(
        hid,
        "paste",
        lambda permit, text: hid.HIDResult(
            ok=True,
            actions=(ForegroundAction.CLIPBOARD, ForegroundAction.KEYBOARD),
        ),
    )
    r = bridge._act_type(ctrl, "e1", "你好")
    assert r["success"] is True
    assert r["via"] == "coord_clipboard"


def test_type_skips_message_when_control_has_no_own_hwnd(bridge, monkeypatch):
    """取不到自身 HWND（自绘/XAML）→ 不投递，直接走粘贴；顶层窗口不能代收。"""
    ctrl = _FakeControl("输入框", "EditControl")  # hwnd=0
    bridge._last_meta["e1"] = {"patterns": []}
    bridge._permit = _permit(set(ForegroundAction))
    posted: list[tuple] = []
    monkeypatch.setattr(hid, "post_text", lambda *a, **k: posted.append(a))
    monkeypatch.setattr(
        hid,
        "set_focus",
        lambda permit, control: hid.HIDResult(
            ok=True, actions=(ForegroundAction.ACTIVATE,)
        ),
    )
    monkeypatch.setattr(
        hid,
        "paste",
        lambda permit, text: hid.HIDResult(
            ok=True,
            actions=(ForegroundAction.CLIPBOARD, ForegroundAction.KEYBOARD),
        ),
    )
    r = bridge._act_type(ctrl, "e1", "你好")
    assert r["via"] == "coord_clipboard"
    assert posted == []


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
