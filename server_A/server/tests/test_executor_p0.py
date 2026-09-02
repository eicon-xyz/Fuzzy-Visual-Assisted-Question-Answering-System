"""P0 接线级改造（报告 §四 0.1–0.8）单元测试 —— Linux/无 pyautogui 环境可跑。

策略：
  * uia_bridge 层：完全用 fake uiautomation 控件树（与 test_uia_bridge.py 同款思路），
    覆盖 0.2 验证链 / 0.3 id×name 交叉验证 / 0.5 ExpandCollapse / 0.8 actionability 谓词。
  * agent 层：仅当真实 pyautogui 不可导入时注入桩模块，再 import ExecutionAgent，
    并给每个用例注入 fake UIABridge，避免真实键鼠/屏幕副作用。
"""
from __future__ import annotations

import platform
import sys
import types

import pytest

# ── 让 agent.py 在缺 pyautogui 的 Linux 上可导入（仅缺啥补啥，不覆盖真实模块）──
for _mod_name in ("pyautogui", "pygetwindow", "mouseinfo"):
    try:
        __import__(_mod_name)
    except Exception:
        _stub = types.ModuleType(_mod_name)

        def _stub_attr(_n):
            def _noop(*a, **k):
                return None

            return _noop

        _stub.__getattr__ = _stub_attr  # type: ignore[attr-defined]
        sys.modules[_mod_name] = _stub

from server.models.schemas import UIElement  # noqa: E402
from server.services.executor import agent as agent_mod  # noqa: E402
from server.services.executor.uia_bridge import UIABridge  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# Fake UIA 控件树
# ═══════════════════════════════════════════════════════════════════════════


class _Rect:
    def __init__(self, l, t, r, b):
        self.left, self.top, self.right, self.bottom = l, t, r, b


class _FakeInvokePattern:
    def __init__(self, ctrl, effect=None):
        self._ctrl = ctrl
        self._effect = effect

    def Invoke(self):
        self._ctrl.log.append("invoke")
        if self._effect:
            self._effect(self._ctrl)


class _FakeSelectPattern:
    def __init__(self, ctrl, effect=None):
        self._ctrl = ctrl
        self._effect = effect

    def Select(self):
        self._ctrl.log.append("select")
        if self._effect:
            self._effect(self._ctrl)

    @property
    def IsSelected(self):
        return getattr(self._ctrl, "_selected", False)


class _FakeValuePattern:
    def __init__(self, ctrl):
        self._ctrl = ctrl

    def SetValue(self, v):
        self._ctrl.log.append(("setvalue", v))
        self._ctrl._value = v

    @property
    def Value(self):
        return getattr(self._ctrl, "_value", "")


class _FakeExpandPattern:
    def __init__(self, ctrl, children=None):
        self._ctrl = ctrl
        self._children = list(children or [])

    def Expand(self):
        self._ctrl.log.append("expand")
        self._ctrl._expand_state = "Expanded"
        if self._children:
            self._ctrl._children = list(self._children)

    def Collapse(self):
        self._ctrl.log.append("collapse")
        self._ctrl._expand_state = "Collapsed"

    @property
    def ExpandCollapseState(self):
        return getattr(self._ctrl, "_expand_state", "Collapsed")


class _FakeTogglePattern:
    def __init__(self, ctrl):
        self._ctrl = ctrl

    def Toggle(self):
        self._ctrl.log.append("toggle")
        self._ctrl._toggled = not getattr(self._ctrl, "_toggled", False)


class FakeControl:
    """可编程假 UIA 控件：动作可带 effect 回调改属性，供 diff/验证断言。"""

    def __init__(
        self,
        name="",
        ctype="ButtonControl",
        rect=(0, 0, 50, 20),
        children=(),
        patterns=(),
        enabled=True,
        offscreen=False,
        class_name="DummyClass",
    ):
        self.Name = name
        self.ControlTypeName = ctype
        self.ClassName = class_name
        self.BoundingRectangle = _Rect(*rect)
        self._children = list(children)
        self._patterns = dict(patterns)
        self.IsEnabled = enabled
        self.IsOffscreen = offscreen
        self.log = []

    def GetChildren(self):
        return self._children

    def _get(self, key):
        pat = self._patterns.get(key)
        if pat is None:
            raise RuntimeError(f"no {key}")
        return pat

    def GetInvokePattern(self):
        return self._get("invoke")

    def GetSelectionItemPattern(self):
        return self._get("select")

    def GetTogglePattern(self):
        return self._get("toggle")

    def GetValuePattern(self):
        return self._get("value")

    def GetExpandCollapsePattern(self):
        return self._get("expand")

    def GetScrollPattern(self):
        return self._get("scroll")

    def SetFocus(self):
        self.log.append("focus")

    def ClickablePoint(self):
        r = self.BoundingRectangle
        return ((r.left + r.right) // 2, (r.top + r.bottom) // 2)


def install_fake_uia(monkeypatch, root):
    """让 UIABridge 认为在 Windows + uiautomation 可用。"""
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    auto = types.ModuleType("uiautomation")
    auto.GetForegroundControl = lambda: root
    monkeypatch.setitem(sys.modules, "uiautomation", auto)


def find_el(els, text):
    return next(e for e in els if e.text == text)


# ═══════════════════════════════════════════════════════════════════════════
# 0.2 动作后验证接线
# ═══════════════════════════════════════════════════════════════════════════


def test_act_returns_verification_fields(monkeypatch):
    """act() 成功路径必须带 action_ok/verified/state_changed/prop_diff。"""

    def _rename(c):
        c.Name = "已连接"

    btn = FakeControl("连接")
    btn._patterns["invoke"] = _FakeInvokePattern(btn, _rename)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(btn,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    el = find_el(els, "连接")
    r = b.act(el.element_id, action="click", verify_timeout=0.5)
    assert r["success"] and r["action_ok"] is True
    assert r["verified"] is True
    assert r["state_changed"] is True  # name 连接→已连接
    assert "name" in r["prop_diff"]["changed"]
    assert r["prop_diff"]["before"]["name"] == "连接"
    assert r["prop_diff"]["after"]["name"] == "已连接"


def test_act_state_unchanged_flags_noop(monkeypatch):
    """invoke 后属性无变化 → state_changed=False（供上层判定无效点击）。"""
    btn = FakeControl("按钮", patterns={})
    btn._patterns["invoke"] = _FakeInvokePattern(btn)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(btn,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(find_el(els, "按钮").element_id, verify_timeout=0.3)
    assert r["action_ok"] and r["state_changed"] is False


def test_wait_for_text_polls_without_touching_id_map(monkeypatch):
    """wait_for_text 轮询新快照找文本，但不得打乱主快照 element_id 映射。"""
    btn = FakeControl("确定", patterns={})
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(btn,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    eid = find_el(els, "确定").element_id
    before_map = dict(b._last_controls)

    w = b.wait_for_text("确定", timeout=1.0, interval=0.2)
    assert w["ok"] is True and w["matched"] == "确定"
    assert b._last_controls == before_map  # id 映射未被临时快照污染

    miss = b.wait_for_text("不存在的文本XYZ", timeout=0.4, interval=0.2)
    assert miss["ok"] is False and "within" in miss["reason"]


def test_act_expect_fail_marks_expect_ok(monkeypatch):
    """expect 指向不存在的文本 → expect_ok=False（agent 层据此自动重观察）。"""
    btn = FakeControl("按钮", patterns={})
    btn._patterns["invoke"] = _FakeInvokePattern(btn)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(btn,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(
        find_el(els, "按钮").element_id,
        expect="永远不会出现的文本",
        verify_timeout=0.3,
        expect_timeout=0.4,
    )
    assert r["expect_ok"] is False


# ── agent 层接线：_post_action_result 自动重观察 ──


def _make_agent_with_fake_bridge(fake_bridge):
    a = agent_mod.ExecutionAgent()
    a._uia = fake_bridge
    a.screen_source = "uia"
    el = UIElement(
        element_id="u1", bbox=[10, 10, 60, 30], element_type="button",
        text="确定", confidence=0.9, center=[35, 20],
    )
    a.element_map = {"u1": el}
    return a


class _BridgeStub:
    available = True

    def __init__(self, act_result, wait_result=None):
        self._act_result = act_result
        self._wait_result = wait_result or {"ok": True}
        self.calls = []

    def act(self, element_id, action="click", text=None, expect=None, **kw):
        self.calls.append(("act", element_id, action, expect))
        return dict(self._act_result)

    def wait_for_text(self, text, timeout=3.0, interval=0.4):
        self.calls.append(("wait_for_text", text))
        return dict(self._wait_result)


def test_agent_click_surfaces_verification_fields(monkeypatch):
    bridge = _BridgeStub(
        {"success": True, "via": "uia_invoke", "action_ok": True, "verified": True,
         "state_changed": True, "prop_diff": {"changed": ["name"], "before": {}, "after": {}}}
    )
    a = _make_agent_with_fake_bridge(bridge)
    r = a._do_click("u1")
    assert r["success"] and r["action_ok"] and r["verified"] and r["state_changed"]
    assert "prop_diff" in r
    assert ("act", "u1", "click", None) in bridge.calls


def test_agent_click_expect_fail_triggers_reobserve(monkeypatch):
    """expect 未满足 → 自动重观察（reobserved + new_elements + ids_refreshed + hint）。"""
    bridge = _BridgeStub(
        {"success": True, "via": "uia_invoke", "action_ok": True, "verified": True,
         "state_changed": False, "expect_ok": False,
         "expect_detail": {"ok": False, "reason": "timeout"}},
        wait_result={"ok": False, "reason": "timeout"},
    )
    a = _make_agent_with_fake_bridge(bridge)
    observed = {}

    def fake_observe():
        observed["called"] = True
        return {"success": True, "elements": [{"id": "u9", "content": "新面板"}]}

    monkeypatch.setattr(a, "_do_get_screen_info", fake_observe)
    r = a._do_click("u1", expect="登录成功")
    assert observed.get("called")
    assert r["expect_ok"] is False
    assert r["reobserved"] and r["ids_refreshed"]
    assert r["new_elements"] == [{"id": "u9", "content": "新面板"}]
    assert "改变策略" in r["hint"]


def test_agent_click_verify_fail_no_change_triggers_reobserve(monkeypatch):
    """verified=false 且 state_changed=false（点了没反应）→ 也自动重观察。"""
    bridge = _BridgeStub(
        {"success": True, "via": "coord", "action_ok": True, "verified": False,
         "verify_reason": "control not ready (disabled/offscreen)", "state_changed": False}
    )
    a = _make_agent_with_fake_bridge(bridge)
    monkeypatch.setattr(
        a, "_do_get_screen_info",
        lambda: {"success": True, "elements": [{"id": "u2", "content": "x"}]},
    )
    r = a._do_click("u1")
    assert r["reobserved"] is True
    assert "控件校验未通过" in r["hint"]
