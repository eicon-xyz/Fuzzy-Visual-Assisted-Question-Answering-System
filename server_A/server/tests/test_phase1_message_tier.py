"""Phase 1 · M1/M2：W 档（投递窗口消息）与 input_mode 分类器。

判据：
  1. W 档无许可 = 拒绝；有许可才投递；投递不被接受 = path_unavailable（不静默转真点击）
  2. ``_act_coord`` 无显式 via 时按 input_mode 选侵入性更低的一档，并把实际档位回在 via
  3. input_mode 是提示：Chromium/XAML→foreground，classic 有子控件→message，
     "最小化"是独立维度（能收消息，但抓不到像素）

全部用假的 win32gui，不碰真实窗口。
"""

from __future__ import annotations

import pytest

from server.services.executor import hid
from server.services.executor.permit import (
    ForegroundAction,
    PermitBroker,
    TaskPolicy,
    derive_policy,
)
from server.services.executor.uia_bridge import UIABridge


class _Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class _FakeControl:
    """够 _control_bbox / _hwnd_of / _props / _check_actionable 用。"""

    def __init__(self, hwnd=0x1234, rect=(100, 100, 300, 200), name="按钮"):
        self.Name = name
        self.ControlTypeName = "ButtonControl"
        self.BoundingRectangle = _Rect(*rect)
        self.IsEnabled = True
        self.IsOffscreen = False
        self.NativeWindowHandle = hwnd

    def GetTopLevelControl(self):
        return self

    def GetChildren(self):
        return []


class _FakeWin32Gui:
    """只实现分类与投递用到的那几个 API。"""

    def __init__(self, class_name="Button", children=2, iconic=False, post_ok=True):
        self.class_name = class_name
        self.children = children
        self.iconic = iconic
        self.post_ok = post_ok
        self.posted: list[tuple] = []

    def IsWindow(self, hwnd):
        return True

    def IsIconic(self, hwnd):
        return self.iconic

    def GetClassName(self, hwnd):
        return self.class_name

    def EnumChildWindows(self, hwnd, cb, extra):
        for i in range(self.children):
            cb(1000 + i, extra)
        return True

    def ScreenToClient(self, hwnd, point):
        return (point[0] - 100, point[1] - 80)

    def PostMessage(self, hwnd, msg, wparam, lparam):
        self.posted.append((hwnd, msg, wparam, lparam))
        return self.post_ok


@pytest.fixture
def gui(monkeypatch):
    fake = _FakeWin32Gui()
    # 两个模块各自有一份 lazy 取用：hid 负责投递，uia_bridge 负责分类
    monkeypatch.setattr(hid, "_win32gui", lambda: fake)
    monkeypatch.setattr(
        "server.services.executor.uia_bridge._win32gui", lambda: fake
    )
    return fake


@pytest.fixture
def bridge(monkeypatch, gui):
    b = UIABridge()
    b._available = True
    b._permit = _permit({ForegroundAction.WINDOW_MESSAGE})
    return b


def _permit(actions):
    return PermitBroker().resolve(
        TaskPolicy(task_id="t", actions=frozenset(actions)), consent=True
    )


# ── hid.post_click / post_text ─────────────────────────────────────────────


def test_post_click_refused_without_permit(gui):
    r = hid.post_click(None, 0x1234, (150, 120))
    assert r.ok is False
    assert r.error_code == "permit_required"
    assert r.to_dict()["required_actions"] == ["window_message"]
    assert gui.posted == [], "拒绝时绝不能真的投递"


def test_post_click_permission_isolated_from_pointer():
    """有 POINTER 不等于能投递消息（反向：投递 ≠ 搬光标）。"""
    p = _permit({ForegroundAction.POINTER})
    r = hid.post_click(p, 0x1234, (150, 120))
    assert r.error_code == "permit_required"


def test_post_click_posts_window_messages_with_client_coords(gui):
    p = _permit({ForegroundAction.WINDOW_MESSAGE})
    r = hid.post_click(p, 0x1234, (150, 120), button="left", clicks=1)
    assert r.ok is True
    assert r.detail["via"] == "message"
    assert r.detail["client"] == [50, 40]  # ScreenToClient 之后
    msgs = [m for _, m, _, _ in gui.posted]
    assert msgs == [hid.WM_LBUTTONDOWN, hid.WM_LBUTTONUP]
    # lparam = MAKELONG(50, 40)
    assert gui.posted[0][3] == ((40 & 0xFFFF) << 16) | (50 & 0xFFFF)


def test_post_click_right_button_messages(gui):
    p = _permit({ForegroundAction.WINDOW_MESSAGE})
    hid.post_click(p, 0x1234, (150, 120), button="right")
    assert [m for _, m, _, _ in gui.posted] == [hid.WM_RBUTTONDOWN, hid.WM_RBUTTONUP]


def test_post_click_rejected_by_target_is_path_unavailable(monkeypatch):
    fake = _FakeWin32Gui(post_ok=False)
    monkeypatch.setattr(hid, "_win32gui", lambda: fake)
    p = _permit({ForegroundAction.WINDOW_MESSAGE})
    r = hid.post_click(p, 0x1234, (150, 120))
    assert r.ok is False
    assert r.error_code == "path_unavailable", "投递不被接受必须显式报告，不许转真点击"


def test_post_click_without_hwnd_is_path_unavailable(gui):
    p = _permit({ForegroundAction.WINDOW_MESSAGE})
    r = hid.post_click(p, 0, (150, 120))
    assert r.error_code == "path_unavailable"


def test_post_text_posts_wm_char_per_char(gui):
    p = _permit({ForegroundAction.WINDOW_MESSAGE})
    r = hid.post_text(p, 0x1234, "你好A")
    assert r.ok is True
    assert [m for _, m, _, _ in gui.posted] == [hid.WM_CHAR] * 3
    assert [w for _, _, w, _ in gui.posted] == [ord("你"), ord("好"), ord("A")]


def test_post_text_refused_without_permit(gui):
    assert hid.post_text(None, 0x1234, "x").error_code == "permit_required"
    assert gui.posted == []


# ── input_mode 分类 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cls", "children", "expected"),
    [
        ("Button", 3, "message"),
        ("CabinetWClass", 12, "message"),
        ("Chrome_WidgetWin_1", 1, "foreground"),
        ("ApplicationFrameWindow", 3, "foreground"),
        ("Windows.UI.Core.CoreWindow", 0, "foreground"),
        ("SomeUnknownClass", 0, "unknown"),
    ],
)
def test_input_mode_classification(monkeypatch, cls, children, expected):
    fake = _FakeWin32Gui(class_name=cls, children=children)
    monkeypatch.setattr(
        "server.services.executor.uia_bridge._win32gui", lambda: fake
    )
    b = UIABridge()
    m = b.input_mode(0x1234)
    assert m["mode"] == expected
    assert m["why"].startswith(("classic:", "class:", "no_child:"))


def test_input_mode_minimized_is_independent_dimension(monkeypatch):
    """最小化不影响"能不能投递消息"，只影响像素。"""
    fake = _FakeWin32Gui(class_name="Button", children=2, iconic=True)
    monkeypatch.setattr(
        "server.services.executor.uia_bridge._win32gui", lambda: fake
    )
    b = UIABridge()
    m = b.input_mode(0x1234)
    assert m["mode"] == "message"
    assert m["minimized"] is True
    assert "restore" in m["hint"]


def test_input_mode_without_hwnd(monkeypatch):
    b = UIABridge()
    assert b.input_mode(0)["mode"] == "unknown"
    assert b.input_mode(0)["minimized"] is False


def test_input_mode_cache_does_not_freeze_minimized_state(monkeypatch):
    fake = _FakeWin32Gui(class_name="Button", children=2, iconic=False)
    monkeypatch.setattr(
        "server.services.executor.uia_bridge._win32gui", lambda: fake
    )
    b = UIABridge()
    assert b.input_mode(0x1234)["minimized"] is False
    fake.iconic = True
    assert b.input_mode(0x1234)["minimized"] is True


def test_list_windows_surfaces_input_mode_and_hides_hwnd(bridge, gui):
    """windows[] 是模型看的投影：要有 input_mode，但不能有 hwnd（会被编造）。"""
    row = {
        "wid": "w1",
        "title": "记事本",
        "bbox": [0, 0, 800, 600],
        "active": True,
        "items": 3,
        "expandable": True,
        "hwnd": 0x1234,
    }
    bridge._scan_top_windows = lambda: [(object(), dict(row))]
    out = bridge.list_windows()
    assert out[0]["input_mode"] == "message"
    assert "hwnd" not in out[0]


def test_list_windows_marks_minimized(bridge, gui):
    gui.iconic = True
    row = {
        "wid": "w1",
        "title": "记事本",
        "bbox": [0, 0, 800, 600],
        "active": False,
        "items": 3,
        "expandable": True,
        "hwnd": 0x1234,
    }
    bridge._scan_top_windows = lambda: [(object(), dict(row))]
    out = bridge.list_windows()
    assert out[0]["minimized"] is True


# ── _act_coord 选路 ───────────────────────────────────────────────────────


def test_act_coord_explicit_message_uses_post_click(bridge, gui, monkeypatch):
    calls = []
    monkeypatch.setattr(hid, "click", lambda *a, **k: calls.append("sendinput"))
    r = bridge._act_coord(_FakeControl(), "e1", via="message")
    assert r["success"] is True
    assert r["via"] == "message"
    assert r["posted"] is True
    assert calls == [], "W 档不许同时触发 SendInput"


def test_act_coord_auto_picks_message_on_classic_window(bridge, gui, monkeypatch):
    calls = []
    monkeypatch.setattr(hid, "click", lambda *a, **k: calls.append("sendinput"))
    r = bridge._act_coord(_FakeControl(), "e1", via=None)
    assert r["via"] == "message"
    assert calls == []


def test_act_coord_auto_picks_coord_on_chromium(bridge, gui, monkeypatch):
    gui.class_name = "Chrome_WidgetWin_1"
    calls = []
    monkeypatch.setattr(
        hid, "click", lambda *a, **k: (calls.append("sendinput"), hid.HIDResult(ok=True))[1]
    )
    r = bridge._act_coord(_FakeControl(), "e1", via=None)
    assert r["via"] == "coord"
    assert calls == ["sendinput"]


def test_act_coord_message_without_hwnd_reports_path_unavailable(bridge, gui):
    r = bridge._act_coord(_FakeControl(hwnd=0), "e1", via="message")
    assert r["success"] is False
    assert r["error_code"] == "path_unavailable"
    assert "coordinate" in r["hint"]


def test_act_message_state_unchanged_offers_next_via(bridge, gui):
    """投递成功但控件属性零变化 → 给 hint + next_via，而不是静默改路。"""
    ctrl = _FakeControl()
    bridge._handles["e1"] = ctrl
    bridge._last_meta["e1"] = {"patterns": [], "type": "ButtonControl"}
    r = bridge.act("e1", action="click", via="message", action_timeout=0.1)
    assert r["success"] is True
    assert r["via"] == "message"
    assert r["state_changed"] is False
    assert r.get("next_via") == "coordinate"


# ── 策略派生 ──────────────────────────────────────────────────────────────


def test_policy_implies_window_message_from_pointer():
    p = derive_policy("t", "双击桌面图标", [])
    assert ForegroundAction.POINTER in p.actions
    assert ForegroundAction.WINDOW_MESSAGE in p.actions
    assert any("window_message" in r for r in p.reasons)


def test_policy_does_not_grant_message_when_nothing_to_operate():
    p = derive_policy("t", "查看当前列表内容", [{"instruction": "读取标题"}])
    assert p.actions == frozenset()
