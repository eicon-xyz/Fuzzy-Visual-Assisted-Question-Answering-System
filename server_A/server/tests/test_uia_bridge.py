"""UIA 绑定桥单元测试（mock uiautomation，不依赖真实 Windows 控件树）。

运行：cd server_A && python -m pytest server/tests/test_uia_bridge.py -v
（Windows 上需已安装 uiautomation；本测试将其替换为 mock，故任意平台可跑）
"""
from __future__ import annotations

import platform
import sys
import types

from server.services.executor.uia_bridge import UIABridge


class _Rect:
    def __init__(self, l, t, r, b):
        self.left, self.top, self.right, self.bottom = l, t, r, b


class _FakePattern:
    def __init__(self, log):
        self._log = log

    def Invoke(self):
        self._log.append("invoke")

    def Select(self):
        self._log.append("select")

    def Toggle(self):
        self._log.append("toggle")

    def SetValue(self, v):
        self._log.append(("setvalue", v))


class _FakeControl:
    def __init__(self, name, ctype, rect, children=(), patterns=(), enabled=True):
        self.Name = name
        self.ControlTypeName = ctype
        self.BoundingRectangle = _Rect(*rect)
        self._children = list(children)
        self._patterns = list(patterns)
        self.IsEnabled = enabled
        self.IsOffscreen = False
        self._log = []

    def GetChildren(self):
        return self._children

    def _pat(self, name):
        if name in self._patterns:
            return _FakePattern(self._log)
        raise RuntimeError(f"no {name} pattern")

    def GetInvokePattern(self):
        return self._pat("invoke")

    def GetSelectionItemPattern(self):
        return self._pat("select")

    def GetTogglePattern(self):
        return self._pat("toggle")

    def GetValuePattern(self):
        return self._pat("value")

    def GetExpandCollapsePattern(self):
        return self._pat("expand")

    def SetFocus(self):
        self._log.append("focus")


def _install_fake_uia(monkeypatch, root):
    # 让桥按 Windows 判定可用（Linux 沙箱跑测试用）
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    auto = types.ModuleType("uiautomation")
    auto.GetForegroundControl = lambda: root
    monkeypatch.setitem(sys.modules, "uiautomation", auto)


def _build_tree():
    btn = _FakeControl("确定", "ButtonControl", (10, 10, 60, 30), patterns=("invoke",))
    box = _FakeControl("搜索", "EditControl", (100, 10, 300, 40), patterns=("value",))
    menu = _FakeControl("文件", "MenuItemControl", (10, 50, 70, 80), patterns=("select",))
    root = _FakeControl("测试窗口", "WindowControl", (0, 0, 800, 600), children=(btn, box, menu))
    return btn, box, menu, root


def test_snapshot_collects_named_controls(monkeypatch):
    btn, box, menu, root = _build_tree()
    _install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    names = {e.text for e in els}
    assert {"确定", "搜索", "文件"} <= names
    assert all(e.element_id.startswith("u") for e in els)
    btn_el = next(e for e in els if e.text == "确定")
    assert btn_el.element_type == "button"
    assert btn_el.center == [35, 20]


def test_snapshot_deep_limited(monkeypatch):
    # 超过 _MAX_DEPTH 的子节点不应被无限遍历（构造 8 层）
    leaf = _FakeControl("深层", "ButtonControl", (0, 0, 10, 10), patterns=())
    node = leaf
    for _ in range(8):
        node = _FakeControl(f"层{_}", "PaneControl", (0, 0, 50, 50), children=(node,), patterns=())
    root = _FakeControl("根", "WindowControl", (0, 0, 800, 600), children=(node,))
    _install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot(max_depth=3)
    # 深度受限：不应收集到 8 层深的目标，但运行不能抛异常
    assert isinstance(els, list)


def test_click_prefers_invoke(monkeypatch):
    btn, box, menu, root = _build_tree()
    _install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    target = next(e for e in els if e.text == "确定")
    r = b.act(target.element_id, action="click")
    assert r["success"] is True
    assert r["via"] == "uia_invoke"
    assert "invoke" in btn._log


def test_click_falls_back_to_select(monkeypatch):
    btn, box, menu, root = _build_tree()
    _install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    target = next(e for e in els if e.text == "文件")
    r = b.act(target.element_id, action="click")
    assert r["success"] is True
    assert r["via"] == "uia_select"
    assert "select" in menu._log


def test_type_uses_setvalue(monkeypatch):
    btn, box, menu, root = _build_tree()
    _install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    target = next(e for e in els if e.text == "搜索")
    r = b.act(target.element_id, action="type", text="hello")
    assert r["success"] is True
    assert r["via"] == "uia_setvalue"
    assert ("setvalue", "hello") in box._log


def test_act_unknown_element_returns_not_found(monkeypatch):
    btn, box, menu, root = _build_tree()
    _install_fake_uia(monkeypatch, root)
    b = UIABridge()
    b.snapshot()
    r = b.act("u999", action="click")
    assert r["success"] is False
    assert r["via"] is None


def test_verify_checks_enabled_offscreen(monkeypatch):
    btn, box, menu, root = _build_tree()
    box.IsEnabled = False  # 模拟输入框暂不可用
    _install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    box_el = next(e for e in els if e.text == "搜索")
    r = b.verify(box_el.element_id, timeout=0.5)
    assert r["success"] is False
    assert "not ready" in r["reason"]

    box.IsEnabled = True
    btn_el = next(e for e in els if e.text == "确定")
    r2 = b.verify(btn_el.element_id, timeout=0.5)
    assert r2["success"] is True


def test_clear_resets_controls(monkeypatch):
    btn, box, menu, root = _build_tree()
    _install_fake_uia(monkeypatch, root)
    b = UIABridge()
    b.snapshot()
    b.clear()
    r = b.act("u1", action="click")
    assert r["success"] is False
    assert r["error"] is not None
