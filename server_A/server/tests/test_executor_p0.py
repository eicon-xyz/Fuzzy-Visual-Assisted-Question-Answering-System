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
    assert w["ok"] is True and w["name"] == "确定"
    assert b._last_controls == before_map  # id 映射未被临时扫描污染

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

    def clear(self):
        pass


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


# ═══════════════════════════════════════════════════════════════════════════
# 0.1 感知序列化：投影字段 + 10 类 ControlType 白名单
# ═══════════════════════════════════════════════════════════════════════════


def _projection_tree():
    btn = FakeControl("确定", ctype="ButtonControl", rect=(10, 10, 60, 30))
    btn._patterns["invoke"] = _FakeInvokePattern(btn)
    edit = FakeControl("搜索", ctype="EditControl", rect=(100, 10, 300, 40))
    edit._patterns["value"] = _FakeValuePattern(edit)
    label = FakeControl("只读提示文本", ctype="TextControl", rect=(10, 60, 200, 80))
    combo = FakeControl("", ctype="ComboBoxControl", rect=(400, 10, 500, 40))  # 无名白名单
    noise = FakeControl("布局层", ctype="PaneControl", rect=(0, 0, 800, 600))
    root = FakeControl("主窗口", ctype="WindowControl", rect=(0, 0, 800, 600),
                       children=(btn, edit, label, combo, noise))
    return root, btn, edit


def test_projection_fields_and_whitelist(monkeypatch):
    """投影含 type/name/class/enabled/patterns/相对 bbox；白名单无名控件保留、
    无交互纯文本与布局 Pane 被过滤。"""
    root, btn, edit = _projection_tree()
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    b.snapshot()
    proj = b.last_projection()
    ids = {p["id"]: p for p in proj}
    by_name = {p["name"]: p for p in proj}
    assert "只读提示文本" not in by_name  # 非交互 Text 不进投影
    assert "布局层" not in by_name       # Pane 无 pattern 不进投影

    p_btn = by_name["确定"]
    assert p_btn["type"] == "button"
    assert p_btn["class"] == "DummyClass"
    assert p_btn["enabled"] is True
    assert p_btn["patterns"] == ["invoke"]
    assert p_btn["bbox"] == [10, 10, 50, 20]  # 相对窗口 [左,上,宽,高]

    p_edit = by_name["搜索"]
    assert p_edit["type"] == "edit" and "value" in p_edit["patterns"]

    # 无名 ComboBox 靠白名单保留
    combo_entries = [p for p in proj if p["type"] == "combobox"]
    assert len(combo_entries) == 1 and combo_entries[0]["name"] == ""

    # element_map 与投影 id 对齐
    assert set(ids) == set(b._last_controls)


def test_agent_get_screen_info_returns_projection(monkeypatch):
    """UIA 分支返回体从 {id,content}×30 升级为投影字段列表。"""
    root, btn, edit = _projection_tree()
    install_fake_uia(monkeypatch, root)
    # 屏蔽观察前的键鼠副作用（Linux 走模块桩；Windows 真模块时替换 press）
    import pyautogui as _pag

    monkeypatch.setattr(_pag, "press", lambda *a, **k: None)
    a = agent_mod.ExecutionAgent()
    result = a._do_get_screen_info()
    assert result["success"] and result["source"] == "uia"
    names = {e.get("name") for e in result["elements"]}
    assert {"确定", "搜索"} <= names
    entry = next(e for e in result["elements"] if e["name"] == "确定")
    assert entry["type"] == "button" and "patterns" in entry and "bbox" in entry
    assert "left_ids" not in entry and "content" not in entry  # 死条款字段已删
    assert result["window_size"] == [800, 600]
    assert a.screen_source == "uia"
    # element_map 键与投影 id 一致，click 可直接消费
    assert set(a.element_map) >= {entry["id"]}


def test_prioritize_projection_caps_and_orders():
    """超 40 个：可交互优先入选，结果保持快照（空间）顺序。"""
    a = agent_mod.ExecutionAgent()
    proj = []
    for i in range(50):
        proj.append({
            "id": f"u{i + 1}", "type": "text", "name": f"n{i}", "class": "",
            "enabled": True, "patterns": ["invoke"] if i >= 20 else [],
            "bbox": [i, 0, 10, 10],
        })
    out = a._prioritize_projection(proj)
    assert len(out) == a._SCREEN_PROJECTION_LIMIT
    kept_ids = [e["id"] for e in out]
    # 全部可交互（u21..u50 共 30 个）必须入选，且按原顺序排列
    interactive_kept = [i for i in kept_ids if int(i[1:]) > 20]
    assert len(interactive_kept) == 30
    assert kept_ids == sorted(kept_ids, key=lambda s: int(s[1:]))


# ═══════════════════════════════════════════════════════════════════════════
# 0.4 零 LLM 卡死检测
# ═══════════════════════════════════════════════════════════════════════════

LD = agent_mod._LoopDetector


def _el(name, bbox=(0, 0, 10, 10)):
    return {"type": "button", "name": name, "bbox": list(bbox)}


def test_repeat_thresholds_tiered_nudge():
    d = LD()
    for i in range(4):
        d.record_action("click", {"element_id": "u1"}, True)
    assert d.build_nudge() == ""  # 4 次未触阈值
    d.record_action("click", {"element_id": "u1"}, True)  # 5
    assert "已连续 5 次" in d.build_nudge()
    for i in range(3):  # 8 → 强制换策略级
        d.record_action("click", {"element_id": "u1"}, True)
    n2 = d.build_nudge()
    assert "连续 8 次" in n2 and "改变方案" in n2
    for i in range(4):  # 12 → 熔断级
        d.record_action("click", {"element_id": "u1"}, True)
    n3 = d.build_nudge()
    assert "已判定卡死" in n3
    # 不同参数 = 不同动作哈希，重复计数被打断
    d.record_action("click", {"element_id": "u2"}, True)
    assert d.build_nudge() == ""


def test_window_slides():
    d = LD()
    for _ in range(d.WINDOW + 5):
        d.record_action("click", {"element_id": "u1"}, True)
    # 滑窗 maxlen=20，重复计数封顶在窗口大小
    assert d.repeat_count() == d.WINDOW


def test_wait_not_counted():
    d = LD()
    for _ in range(10):
        d.record_action("wait", {"seconds": 2}, True)
    assert d.repeat_count() == 0


def test_observation_stagnation_detection():
    d = LD()
    snap = [_el("确定"), _el("取消", (60, 0, 10, 10))]
    for _ in range(5):  # 前 5 次：4 次「不变」，未触阈值
        d.record_observation(snap)
    assert "环境停滞" not in d.build_nudge()
    d.record_observation(snap)  # 第 6 次 → 连续 5 次不变，触发
    assert "环境停滞" in d.build_nudge()
    # 界面变化 → 计数清零
    d.record_observation([_el("新页面")])
    assert "环境停滞" not in d.build_nudge()


def test_observation_fingerprint_ignores_id_renumbering():
    """UIA id 每次重编号（u1..uN），指纹只看内容：内容不变 → 停滞可检出。"""
    fp1 = LD.observation_fingerprint([{"id": "u1", "type": "button", "name": "确定", "bbox": [0, 0, 5, 5]}])
    fp2 = LD.observation_fingerprint([{"id": "u7", "type": "button", "name": "确定", "bbox": [0, 0, 5, 5]}])
    assert fp1 == fp2
    fp3 = LD.observation_fingerprint([{"id": "u1", "type": "button", "name": "取消", "bbox": [0, 0, 5, 5]}])
    assert fp1 != fp3


def test_fail_streak_replan_suggestion():
    d = LD()
    d.record_action("click", {"element_id": "u1"}, False)
    d.record_action("click", {"element_id": "u2"}, False)
    assert "REPLAN" not in d.build_nudge()
    d.record_action("type_text", {"element_id": "u3", "text": "x"}, False)
    assert "REPLAN SUGGESTED" in d.build_nudge()
    d.record_action("click", {"element_id": "u4"}, True)  # 成功清零
    assert "REPLAN" not in d.build_nudge()


# ═══════════════════════════════════════════════════════════════════════════
# 0.3 id×name 交叉验证（UFO _verify_id）
# ═══════════════════════════════════════════════════════════════════════════


def _click_ok_bridge():
    return _BridgeStub(
        {"success": True, "via": "uia_invoke", "action_ok": True,
         "verified": True, "state_changed": True}
    )


def test_name_guard_rejects_mismatch_and_reports_real_name():
    """id 指向「确定」但 LLM 说要点「取消」→ 拒绝执行并回报真名。"""
    bridge = _click_ok_bridge()
    a = _make_agent_with_fake_bridge(bridge)
    r = a._do_click("u1", name="取消")
    assert r["success"] is False
    assert "NAME_MISMATCH" in r["error"]
    assert r["actual_name"] == "确定"
    assert "hint" in r
    assert bridge.calls == []  # 动作未被下发


def test_name_guard_accepts_exact_contains_and_case():
    a = _make_agent_with_fake_bridge(_click_ok_bridge())
    assert a._do_click("u1", name="确定")["success"] is True
    assert a._do_click("u1", name="确")["success"] is True      # 部分包含
    a.element_map["u1"].text = "OK 确定"
    assert a._do_click("u1", name="确定")["success"] is True    # 双向包含


def test_name_guard_skipped_without_name_and_warns_on_unnamed():
    a = _make_agent_with_fake_bridge(_click_ok_bridge())
    r1 = a._do_click("u1")  # 不带 name：不阻断（向后兼容）
    assert r1["success"] is True
    a.element_map["u1"].text = ""  # 无名控件 + 带 name → 放行但提醒无法核对
    a._uia = _click_ok_bridge()
    r2 = a._do_click("u1", name="保存")
    assert r2["success"] is True and "未做 id×name 核对" in str(r2.get("warning", ""))


def test_name_guard_applies_to_type_text():
    a = _make_agent_with_fake_bridge(_click_ok_bridge())
    r = a._do_type_text("u1", "hello", name="提交按钮")
    assert r["success"] is False and "NAME_MISMATCH" in r["error"]
    assert r["actual_name"] == "确定"


def test_dispatch_click_forwards_name(monkeypatch):
    """dispatch_tool 把 name 参数透传到 _do_click。"""
    a = _make_agent_with_fake_bridge(_click_ok_bridge())
    seen = {}
    real = a._do_click

    def spy(element_id, double=False, expect=None, name=None):
        seen["name"] = name
        seen["expect"] = expect
        return real(element_id, double, expect, name)

    monkeypatch.setattr(a, "_do_click", spy)
    a.dispatch_tool("click", {"element_id": "u1", "name": "确定", "expect": "x"})
    assert seen == {"name": "确定", "expect": "x"}


def test_schemas_require_name_for_element_actions():
    """click/double_click/type_text 的 schema 均要求 name 参数。"""
    a = agent_mod.ExecutionAgent()
    tools = {t["function"]["name"]: t["function"] for t in a.tools}
    for name in ("click", "double_click", "type_text"):
        fn = tools[name]
        assert "name" in fn["parameters"]["properties"], name
        assert "name" in fn["parameters"]["required"], name


# ═══════════════════════════════════════════════════════════════════════════
# 0.5 ExpandCollapse 入 act() + 菜单自动重观察 + 删全局 ESC
# ═══════════════════════════════════════════════════════════════════════════


def test_click_on_expandcollapse_control_expands(monkeypatch):
    """无 Invoke/Select/Toggle 但有 ExpandCollapse 的菜单头：click=Expand。"""
    submenu = FakeControl("新建", ctype="MenuItemControl", rect=(0, 50, 60, 70))
    header = FakeControl("文件", ctype="MenuItemControl", rect=(0, 20, 50, 45))
    header._patterns["expand"] = _FakeExpandPattern(header, children=[submenu])
    root = FakeControl("记事本", ctype="WindowControl", rect=(0, 0, 800, 600),
                       children=(header,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(find_el(els, "文件").element_id, action="click", verify_timeout=0.3)
    assert r["success"] and r["via"] == "uia_expand"
    assert "expand" in header.log
    assert r["state_changed"] is True          # expand 属性 Collapsed→Expanded
    assert r["prop_diff"]["after"]["expand"] == "Expanded"
    # 再点一次：已展开则不重复 Expand（幂等）
    header.log.clear()
    r2 = b.act(find_el(els, "文件").element_id, action="click", verify_timeout=0.3)
    assert r2["via"] == "uia_expand" and "expand" not in header.log


def test_act_explicit_expand_and_collapse(monkeypatch):
    combo = FakeControl("", ctype="ComboBoxControl", rect=(10, 10, 120, 40))
    combo._patterns["expand"] = _FakeExpandPattern(combo)
    plain = FakeControl("按钮", ctype="ButtonControl", rect=(0, 0, 10, 10))
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 400, 300),
                       children=(combo, plain))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    combo_el = next(e for e in els if e.element_type == "dropdown")
    r = b.act(combo_el.element_id, action="expand", verify_timeout=0.2)
    assert r["success"] and r["via"] == "uia_expand"
    r2 = b.act(combo_el.element_id, action="collapse", verify_timeout=0.2)
    assert r2["success"] and r2["via"] == "uia_collapse"
    # 无 ExpandCollapse pattern 的普通按钮显式 expand → 拒绝并给替代提示
    btn_el = find_el(els, "按钮")
    r3 = b.act(btn_el.element_id, action="expand", verify_timeout=0.2)
    assert r3["success"] is False and "click" in r3["error"]


def test_agent_menu_click_auto_reobserves(monkeypatch):
    """agent 层：click 触发 uia_expand → 自动重观察附 new_elements + 选择指引。"""
    bridge = _BridgeStub(
        {"success": True, "via": "uia_expand", "action_ok": True,
         "verified": True, "state_changed": True}
    )
    a = _make_agent_with_fake_bridge(bridge)
    monkeypatch.setattr(
        a, "_do_get_screen_info",
        lambda: {"success": True, "elements": [
            {"id": "u5", "type": "menuitem", "name": "新建", "enabled": True, "bbox": [1, 1, 1, 1]}
        ]},
    )
    r = a._do_click("u1", name="确定")
    assert r["success"] and r["expanded"] is True and r["ids_refreshed"] is True
    assert r["new_elements"][0]["name"] == "新建"
    assert "展开" in r["hint"] and "再次 click" in r["hint"]


def test_get_screen_info_no_global_esc(monkeypatch):
    """0.5 红线回归：观察屏幕不得再有全局 ESC 副作用（会关掉刚展开的菜单）。"""
    root, btn, edit = _projection_tree()
    install_fake_uia(monkeypatch, root)
    import pyautogui as _pag

    presses = []
    monkeypatch.setattr(_pag, "press", lambda *a, **k: presses.append(a))
    a = agent_mod.ExecutionAgent()
    result = a._do_get_screen_info()
    assert result["source"] == "uia"
    assert presses == []
    # 源码级双保险：函数体内不再引用 press("esc")
    import inspect

    src = inspect.getsource(agent_mod.ExecutionAgent._do_get_screen_info)
    assert 'press("esc")' not in src and "press('esc')" not in src


# ═══════════════════════════════════════════════════════════════════════════
# 0.6 统一错误契约 {ok, error_code, message, hint}
# ═══════════════════════════════════════════════════════════════════════════


def test_dispatch_unknown_tool_contract():
    a = _make_agent_with_fake_bridge(_BridgeStub({"success": True}))
    r = a.dispatch_tool("no_such_tool", {})
    assert r["ok"] is False
    assert r["error_code"] == "unknown_tool"
    assert r["message"] and "hint" in r and r["hint"]


def test_dispatch_element_not_found_contract():
    a = _make_agent_with_fake_bridge(_BridgeStub({"success": True}))
    r = a.dispatch_tool("click", {"element_id": "u99", "name": "x"})
    assert r["ok"] is False and r["error_code"] == "element_not_found"
    assert "get_screen_info" in r["hint"]


def test_dispatch_name_mismatch_contract():
    a = _make_agent_with_fake_bridge(_BridgeStub({"success": True}))
    r = a.dispatch_tool("click", {"element_id": "u1", "name": "完全不同的名字"})
    assert r["ok"] is False and r["error_code"] == "name_mismatch"
    assert r["actual_name"] == "确定"


def test_dispatch_success_contract_and_control_signal_passthrough():
    a = _make_agent_with_fake_bridge(_click_ok_bridge())
    r = a.dispatch_tool("click", {"element_id": "u1", "name": "确定"})
    assert r["ok"] is True and r["success"] is True
    assert r["error_code"] is None and r["message"] is None
    # 0.7 mark_step_failed：首次拦（giveup_refused_retry），二次直通为控制信号
    f1 = a.dispatch_tool("mark_step_failed", {"reason": "尽力了"})
    assert f1["ok"] is False and f1["error_code"] == "giveup_refused_retry"
    f2 = a.dispatch_tool("mark_step_failed", {"reason": "尽力了"})
    assert f2["__step_failed__"] is True and f2["error_code"] is None


def test_dispatch_exception_becomes_tool_exception_contract(monkeypatch):
    a = _make_agent_with_fake_bridge(_BridgeStub({"success": True}))
    monkeypatch.setattr(
        a, "_dispatch_tool_inner",
        lambda name, args: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    r = a.dispatch_tool("wait", {"seconds": 1})
    assert r["ok"] is False and r["error_code"] == "tool_exception"
    assert "boom" in r["message"] and r["hint"]
    # 循环不崩：dispatch 永不抛异常、永不返回 None


def test_dispatch_yellow_zone_contract(monkeypatch):
    a = _make_agent_with_fake_bridge(_BridgeStub({"success": True}))
    from types import SimpleNamespace

    monkeypatch.setattr(
        agent_mod, "check_step",
        lambda text: SimpleNamespace(level="yellow", reason="发送类操作"),
    )
    r = a.dispatch_tool("click", {"element_id": "u1", "name": "确定"})
    assert r["ok"] is False and r["error_code"] == "confirm_required"
    assert "ask_user" in r["hint"] or "确认" in r["hint"]


# ═══════════════════════════════════════════════════════════════════════════
# 0.7 done 证据化 + report_infeasible / ask_user 终止动作
# ═══════════════════════════════════════════════════════════════════════════

import json as _json  # noqa: E402
from server.models.schemas import ExecutedStep  # noqa: E402


def _scripted_agent(monkeypatch, calls, bridge=None):
    """用脚本化 LLM 回复驱动 execute_step（不发真实 API、不睡眠、不查记忆）。"""
    a = _make_agent_with_fake_bridge(bridge or _click_ok_bridge())
    seq = list(calls)
    idx = [0]

    def fake_llm(msgs):
        i = min(idx[0], len(seq) - 1)
        idx[0] += 1
        name, args = seq[i]
        return _json.dumps({"__tool_call__": True, "name": name, "arguments": args}), None

    monkeypatch.setattr(a, "_call_llm_with_tools", fake_llm)
    monkeypatch.setattr(agent_mod.time, "sleep", lambda s: None)
    # 保留预置 element_map/_uia/screen_source（真实实现会清空并重建）
    monkeypatch.setattr(a, "clear_element_map", lambda: None)

    def _no_memory():
        raise RuntimeError("no memory in test")

    monkeypatch.setattr(agent_mod, "get_retriever", _no_memory)
    return a


def _step(instruction="完成某事"):
    return ExecutedStep(step_index=1, instruction=instruction)


def test_execute_step_done_without_evidence_refused_then_passes(monkeypatch):
    a = _scripted_agent(monkeypatch, [
        ("mark_step_done", {"reason": "应该好了", "evidence": ""}),
        ("mark_step_done", {"reason": "应该好了", "evidence": "窗口标题含'无标题 - 记事本'"}),
    ])
    result = a.execute_step(_step(), goal="g", previous_steps=[])
    assert result.status == "done"
    assert "unverified_done" in (result.evidence or "")  # 拒收一次后的自证 done 打标


def test_execute_step_done_with_action_evidence(monkeypatch):
    a = _scripted_agent(monkeypatch, [
        ("click", {"element_id": "u1", "name": "确定"}),
        ("mark_step_done", {"reason": "点掉了", "evidence": ""}),
    ])
    result = a.execute_step(_step(), goal="g", previous_steps=[])
    assert result.status == "done"
    assert "click→确定" in (result.evidence or "")
    assert "state_changed=True" in (result.evidence or "")
    assert "unverified_done" not in (result.evidence or "")


def test_execute_step_report_infeasible_terminates(monkeypatch):
    a = _scripted_agent(monkeypatch, [
        ("report_infeasible", {"reason": "系统未安装该应用", "tried": "launch_app×2, Win搜索"}),
    ])
    result = a.execute_step(_step(), goal="g", previous_steps=[])
    assert result.status == "failed"
    assert result.terminal_kind == "infeasible"
    assert "[不可行]" in result.action_summary and "launch_app" in result.action_summary


def test_execute_step_ask_user_terminates(monkeypatch):
    a = _scripted_agent(monkeypatch, [
        ("ask_user", {"question": "需要登录，账号密码是什么？"}),
    ])
    result = a.execute_step(_step(), goal="g", previous_steps=[])
    assert result.status == "failed"
    assert result.terminal_kind == "ask_user"
    assert result.user_question == "需要登录，账号密码是什么？"


def test_execute_step_failed_gets_second_chance(monkeypatch):
    a = _scripted_agent(monkeypatch, [
        ("mark_step_failed", {"reason": "点不动"}),
        ("mark_step_failed", {"reason": "点不动"}),
    ])
    result = a.execute_step(_step(), goal="g", previous_steps=[])
    assert result.status == "failed"
    assert result.terminal_kind is None
    assert "点不动" in result.action_summary


def test_engine_terminal_actions_skip_blind_retry(monkeypatch, tmp_path):
    """engine：ask_user/infeasible 不再走同指令盲重试，ask_user 发 step_blocked。"""
    from server.services.executor import engine

    monkeypatch.setenv("HAJIMI_EVAL_DIR", str(tmp_path))  # T1：遥测落盘隔离
    q = engine.register_task("t-terminal")
    calls = {"n": 0}

    def fake_execute_step(self, step, goal, previous_steps, **kw):
        calls["n"] += 1
        step.status = "failed"
        step.terminal_kind = "ask_user"
        step.user_question = "选A还是B？"
        step.action_summary = "[需用户决策] 选A还是B？"
        return step

    import server.services.executor.agent as ag_mod

    monkeypatch.setattr(ag_mod.ExecutionAgent, "execute_step", fake_execute_step)
    monkeypatch.setattr(ag_mod.ExecutionAgent, "close_browser", lambda self: None)
    monkeypatch.setattr(
        engine, "_trigger_memory_extraction_failure", lambda *a, **k: None
    )
    import threading as _th

    engine.run_plan_agent_loop(
        "t-terminal", "g", [{"step_index": 1, "instruction": "做选择"}],
        _th.Event(),
    )
    events = []
    while not q.empty():
        events.append(q.get())
    names = [e["event"] for e in events]
    assert calls["n"] == 1  # 未盲重试
    assert "step_blocked" in names
    blocked = next(e for e in events if e["event"] == "step_blocked")
    assert blocked["data"]["question"] == "选A还是B？"
    assert "task_failed" in names
    engine.unregister_task("t-terminal")


# ═══════════════════════════════════════════════════════════════════════════
# 0.8 Playwright 式 actionability 前置谓词
# ═══════════════════════════════════════════════════════════════════════════


class _ShiftingRectControl(FakeControl):
    """每次取 bbox 都在动（模拟动画中）→ 不满足 Stable。"""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._tick = 0

    @property
    def BoundingRectangle(self):
        self._tick += 1
        d = self._tick * 5
        return _Rect(d, 10, 60 + d, 30)

    @BoundingRectangle.setter
    def BoundingRectangle(self, v):  # 吸收基类 __init__ 的赋值
        pass


class _ObscuredControl(FakeControl):
    def GetClickablePoint(self):
        raise RuntimeError("obscured (element offscreen/covered)")


class _LoadingControl(FakeControl):
    """前 N 次读 IsEnabled=False，之后 True —— 验证等待条件而非等待时间。"""

    def __init__(self, *a, flips=3, **k):
        super().__init__(*a, **k)
        self._flips = flips
        self._reads = 0

    @property
    def IsEnabled(self):
        self._reads += 1
        return self._reads > self._flips

    @IsEnabled.setter
    def IsEnabled(self, v):
        pass


def test_actionability_rejects_disabled(monkeypatch):
    btn = FakeControl("按钮", enabled=False)
    btn._patterns["invoke"] = _FakeInvokePattern(btn)
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 400, 300), children=(btn,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(find_el(els, "按钮").element_id, action_timeout=0.5)
    assert r["success"] is False
    assert r["error_code"] == "not_actionable"
    assert "enabled" in r["missing_predicates"]
    assert "hint" in r
    assert "invoke" not in btn.log  # 谓词不过，动作绝不下发


def test_actionability_rejects_unstable_bbox(monkeypatch):
    moving = _ShiftingRectControl("滑块", rect=(0, 10, 60, 30))
    moving._patterns["invoke"] = _FakeInvokePattern(moving)
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 400, 300), children=(moving,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(els[0].element_id, action_timeout=0.5)
    assert r["success"] is False and "stable" in r["missing_predicates"]


def test_actionability_rejects_obscured_click(monkeypatch):
    obscured = _ObscuredControl("被盖住的按钮")
    obscured._patterns["invoke"] = _FakeInvokePattern(obscured)
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 400, 300), children=(obscured,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(els[0].element_id, action_timeout=0.4)
    assert r["success"] is False and "receives_events" in r["missing_predicates"]


def test_actionability_waits_for_condition_not_time(monkeypatch):
    """加载中的控件（若干次读取后 enabled）：等待谓词满足后才执行动作。"""
    loading = _LoadingControl("稍后就绪", flips=3)
    loading._patterns["invoke"] = _FakeInvokePattern(loading)
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 400, 300), children=(loading,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(els[0].element_id, action_timeout=2.5)
    assert r["success"] is True and r["via"] == "uia_invoke"
    assert "invoke" in loading.log


def test_ambiguous_same_name_flagged_not_blocked(monkeypatch):
    """同名多控件：唯一解析软校验——照常执行但回报歧义数量。"""
    b1 = FakeControl("确定", rect=(0, 0, 40, 20))
    b1._patterns["invoke"] = _FakeInvokePattern(b1)
    b2 = FakeControl("确定", rect=(60, 0, 100, 20))
    b2._patterns["invoke"] = _FakeInvokePattern(b2)
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 400, 300), children=(b1, b2))
    install_fake_uia(monkeypatch, root)
    br = UIABridge()
    els = br.snapshot()
    r = br.act(els[0].element_id, action_timeout=0.4)
    assert r["success"] is True
    assert r["ambiguous_same_name"] == 2


def test_agent_not_actionable_propagates_error_code():
    """agent 层把 not_actionable + hint 透传给统一错误契约。"""
    bridge = _BridgeStub(
        {"success": False, "via": None, "error_code": "not_actionable",
         "error": "element not actionable: missing=enabled (waited 3000ms)",
         "hint": "控件未就绪…换 enabled=true 的同功能控件"}
    )
    a = _make_agent_with_fake_bridge(bridge)
    r = a.dispatch_tool("click", {"element_id": "u1", "name": "确定"})
    assert r["ok"] is False
    assert r["error_code"] == "not_actionable"
    assert "同功能控件" in r["hint"]
