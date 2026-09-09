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


class _FakeRangeValuePattern:
    """B4：RangeValuePattern 假模式，.Value 可写（滑杆/数值）。"""

    def __init__(self, ctrl, initial=0.0, raise_on_set=False):
        self._ctrl = ctrl
        ctrl._range_value = float(initial)
        self._raise = raise_on_set

    @property
    def Value(self):
        return getattr(self._ctrl, "_range_value", 0.0)

    @Value.setter
    def Value(self, v):
        if self._raise:
            raise RuntimeError("range set failed")
        self._ctrl.log.append(("setrange", float(v)))
        self._ctrl._range_value = float(v)


class _FakeWindowPattern:
    """B4：WindowPattern 假模式（Minimize 等原生方法缺失时的回退路径）。"""

    def __init__(self, ctrl):
        self._ctrl = ctrl

    def Close(self):
        self._ctrl.log.append("close")

    def SetWindowVisualState(self, state):
        self._ctrl.log.append(("visual", state))


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

    def GetRangeValuePattern(self):
        return self._get("rangevalue")

    def GetWindowPattern(self):
        return self._get("window")

    def GetTopLevelControl(self):
        return getattr(self, "_top_level", self)

    def Minimize(self):
        self.log.append("minimize")

    def Maximize(self):
        self.log.append("maximize")

    def Restore(self):
        self.log.append("restore")

    def Close(self):
        self.log.append("close")

    def SetFocus(self):
        self.log.append("focus")

    def ClickablePoint(self):
        r = self.BoundingRectangle
        return ((r.left + r.right) // 2, (r.top + r.bottom) // 2)


def install_fake_uia(monkeypatch, root, roots=()):
    """让 UIABridge 认为在 Windows + uiautomation 可用。

    roots：B4 顶层窗口列表（GetRootControl().GetChildren() 返回它们，
    act_window 按 title 匹配走这条路）。
    """
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    auto = types.ModuleType("uiautomation")
    auto.GetForegroundControl = lambda: root
    auto.GetRootControl = lambda: FakeControl("Desktop", ctype="PaneControl", children=tuple(roots))
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
        self.calls_kw = []  # B2: 记录 act 的额外关键字参数（via 透传断言用）

    def act(self, element_id, action="click", text=None, expect=None, **kw):
        self.calls.append(("act", element_id, action, expect))
        self.calls_kw.append(kw)
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
    """dispatch_tool 把 name/expect/via 参数透传到 _do_click。"""
    a = _make_agent_with_fake_bridge(_click_ok_bridge())
    seen = {}
    real = a._do_click

    # B2 决策表语义：_do_click 新增 via 关键字（默认 None），spy 签名同步
    def spy(element_id, double=False, expect=None, name=None, via=None):
        seen["name"] = name
        seen["expect"] = expect
        seen["via"] = via
        return real(element_id, double, expect, name)

    monkeypatch.setattr(a, "_do_click", spy)
    a.dispatch_tool("click", {"element_id": "u1", "name": "确定", "expect": "x"})
    assert seen == {"name": "确定", "expect": "x", "via": None}


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


# ═══════════════════════════════════════════════════════════════════════════
# P0.5-R1 annotated_image 移出 LLM 上下文（台账 A1）
# ═══════════════════════════════════════════════════════════════════════════

import copy as _copy  # noqa: E402
from server.services.executor.agent import (  # noqa: E402
    _LLM_STRIP_KEYS,
    _strip_for_llm,
)


def test_p05_r1_strip_for_llm_pure_function():
    """纯函数：两键都剥、不碰原 dict、无键返回同一对象、非 dict 原样返回。"""
    src = {
        "success": True,
        "annotated_image": "data:image/jpeg;base64,BIGDATA",
        "image_b64": "data:image/jpeg;base64,B64",
        "elements": ["u1"],
    }
    out = _strip_for_llm(src)
    assert "annotated_image" not in out
    assert "image_b64" not in out
    assert out["success"] is True and out["elements"] == ["u1"]
    # 拷贝剥离：原 dict 不被修改
    assert "annotated_image" in src and "image_b64" in src
    # 无两键 → 返回同一对象（等值/同身份）
    d = {"success": True, "elements": ["u1"]}
    assert _strip_for_llm(d) is d
    # 非 dict 原样返回
    assert _strip_for_llm("x") == "x"
    assert _strip_for_llm(None) is None


def test_p05_r1_annotated_image_stripped_from_llm_but_pushed_to_sse(monkeypatch):
    """集成：get_screen_info 带 BIGDATA → on_screenshot 收到，但任一 LLM msgs 不得含之。

    脚本 [get_screen_info → mark_step_done → mark_step_done]：fake _do_get_screen_info
    直供 UIA 观察结果（dispatch 层记账 observation），第一次 done 无证据被 gate 拒收，
    第二次放行（参照 done_without_evidence_refused_then_passes）。
    """
    a = _make_agent_with_fake_bridge(_click_ok_bridge())
    collected = []
    msgs_seen = []

    def fake_observe():
        return {
            "success": True,
            "source": "uia",
            "elements": [{"element_id": "u1", "text": "确定"}],
            "element_count": 2,
            "annotated_image": "data:image/jpeg;base64,BIGDATA",
            "action_summary": "obs",
        }

    monkeypatch.setattr(a, "_do_get_screen_info", fake_observe)

    seq = [
        ("get_screen_info", {}),
        ("mark_step_done", {"reason": "应该好了", "evidence": ""}),
        (
            "mark_step_done",
            {"reason": "应该好了", "evidence": "窗口标题含'无标题 - 记事本'"},
        ),
    ]
    idx = [0]

    def fake_llm(msgs):
        msgs_seen.append(_copy.deepcopy(msgs))
        i = min(idx[0], len(seq) - 1)
        idx[0] += 1
        name, args = seq[i]
        return (
            _json.dumps({"__tool_call__": True, "name": name, "arguments": args}),
            None,
        )

    monkeypatch.setattr(a, "_call_llm_with_tools", fake_llm)
    monkeypatch.setattr(agent_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(a, "clear_element_map", lambda: None)

    def _no_memory():
        raise RuntimeError("no memory in test")

    monkeypatch.setattr(agent_mod, "get_retriever", _no_memory)

    result = a.execute_step(
        _step(),
        goal="g",
        previous_steps=[],
        cancel_event=None,
        on_screenshot=collected.append,
    )
    assert result.status == "done"
    # ① on_screenshot 回调收到 BIGDATA（SSE→B 端路径保留）
    assert collected, "on_screenshot 应收到截图"
    assert any("BIGDATA" in b for b in collected)
    # ② 任一 LLM msgs 序列化后不含 BIGDATA / annotated_image
    assert msgs_seen, "LLM 应至少被调用一次"
    blob = _json.dumps(msgs_seen, ensure_ascii=False)
    assert "BIGDATA" not in blob
    assert "annotated_image" not in blob


# ═══════════════════════════════════════════════════════════════════════════
# P0.5-R2 删除 OmniParser throttle 化石（台账 C3）
# ═══════════════════════════════════════════════════════════════════════════

import inspect as _inspect  # noqa: E402


def test_p05_r2_no_omniparser_throttle_sleep():
    """execute_step 内不得残留 OmniParser 退役化石的 throttle sleep（R2）。

    断言实际调用而非注释文本：T1 已把删除说明写进注释（含化石名
    "throttle OmniParser"），故按「剔除注释后无任何 time.sleep 语句」判定。
    """
    src = _inspect.getsource(agent_mod.ExecutionAgent.execute_step)
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert "time.sleep" not in code


# ═══════════════════════════════════════════════════════════════════════════
# P0.5-B2 决策表 + fail-closed + probe/exec 分离 + 最小逃生舱（台账 B2）
# ═══════════════════════════════════════════════════════════════════════════


class _DeadInvokePattern:
    """Invoke() 抛异常（模拟控件在动作瞬间已销毁/应用无响应）。"""

    def __init__(self, ctrl):
        self._ctrl = ctrl

    def Invoke(self):
        self._ctrl.log.append("invoke")
        raise RuntimeError("dead")


class _ProbeCountingControl(FakeControl):
    """记录 GetInvokePattern 被调次数（探测 vs 执行分离验证）。"""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.invoke_probes = 0

    def GetInvokePattern(self):
        self.invoke_probes += 1
        return super().GetInvokePattern()


def _monkeypatch_click_at(monkeypatch, calls):
    import server.services.executor.clicker as _clicker_mod

    monkeypatch.setattr(_clicker_mod, "click_at", lambda *a, **k: calls.append(a))


def test_p05_b2_menuitem_table_expand_over_invoke(monkeypatch):
    """决策表优先于旧链序：menuitem 同时缓存 invoke+expand → 执行 expand，不是 invoke。"""
    submenu = FakeControl("新建", ctype="MenuItemControl", rect=(0, 50, 60, 70))
    header = FakeControl("文件", ctype="MenuItemControl", rect=(0, 20, 50, 45))
    header._patterns["invoke"] = _FakeInvokePattern(header)
    header._patterns["expand"] = _FakeExpandPattern(header, children=[submenu])
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 800, 600), children=(header,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(find_el(els, "文件").element_id, action="click", verify_timeout=0.3)
    assert r["success"] is True
    assert r["via"] == "uia_expand"
    assert "expand" in header.log
    assert "invoke" not in header.log  # 动词由决策表决定，不再受探测顺序支配


def test_p05_b2_edit_no_candidates_action_ambiguous_no_dispatch(monkeypatch):
    """edit 表空候选 → action_ambiguous，且动作未下发（log 空、click_at 未被调）。"""
    edit = FakeControl("搜索", ctype="EditControl", rect=(10, 10, 200, 40))
    edit._patterns["value"] = _FakeValuePattern(edit)  # 即便有 pattern，edit 无点击语义
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 800, 600), children=(edit,))
    install_fake_uia(monkeypatch, root)
    calls = []
    _monkeypatch_click_at(monkeypatch, calls)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(find_el(els, "搜索").element_id, action="click", action_timeout=0.4)
    assert r["success"] is False
    assert r["error_code"] == "action_ambiguous"
    assert r["via"] is None and r["action_ok"] is False
    assert edit.log == []  # 无任何动作下发
    assert calls == []     # 未落坐标


def test_p05_b2_pane_out_of_table_default_candidates_invoke(monkeypatch):
    """表外类型（pane）缓存 invoke → invoke 执行成功（_DEFAULT_CANDIDATES 生效）。"""
    pane = FakeControl("自定义区域", ctype="PaneControl", rect=(10, 10, 100, 50))
    pane._patterns["invoke"] = _FakeInvokePattern(pane)
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 800, 600), children=(pane,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(find_el(els, "自定义区域").element_id, action="click", verify_timeout=0.3)
    assert r["success"] is True
    assert r["via"] == "uia_invoke"
    assert "invoke" in pane.log


def test_p05_b2_fail_closed_pattern_failed_no_coord_no_retry(monkeypatch):
    """button 表定 invoke，但 Invoke() 抛异常 → pattern_failed：不落坐标、不试其他模式。"""
    btn = FakeControl("确定", ctype="ButtonControl", rect=(10, 10, 60, 30))
    btn._patterns["invoke"] = _DeadInvokePattern(btn)
    btn._patterns["select"] = _FakeSelectPattern(btn)  # 假控件也支持 select，但不得被尝试
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 800, 600), children=(btn,))
    install_fake_uia(monkeypatch, root)
    calls = []
    _monkeypatch_click_at(monkeypatch, calls)
    b = UIABridge()
    els = b.snapshot()
    r = b.act(find_el(els, "确定").element_id, action="click", action_timeout=0.4)
    assert r["success"] is False
    assert r["error_code"] == "pattern_failed"
    assert "invoke exec failed" in r["error"]
    assert r["via"] is None and r["action_ok"] is False
    assert calls == []            # 未落坐标（双触发/坐标失效风险归零）
    assert "select" not in btn.log  # fail-closed：绝不落到下一模式
    assert "invoke" in btn.log      # invoke 确实执行到（已生效才抛错）


def test_p05_b2_explicit_coordinate_via_passthrough(monkeypatch):
    """最小逃生舱：dispatch click 传 via='coordinate' → act 收到 via 并直走 coord。"""
    bridge = _BridgeStub(
        {"success": True, "via": "coord", "action_ok": True, "verified": True,
         "state_changed": True}
    )
    a = _make_agent_with_fake_bridge(bridge)
    r = a.dispatch_tool("click", {"element_id": "u1", "name": "确定", "via": "coordinate"})
    assert r["success"] is True
    assert any(kw.get("via") == "coordinate" for kw in bridge.calls_kw)


def test_p05_b2_exec_no_reprobe_uses_cached(monkeypatch):
    """执行期不再重复探测：一次 act(click) 内 GetInvokePattern 调用 ≤1（探测全走缓存）。"""
    btn = _ProbeCountingControl("确定", ctype="ButtonControl", rect=(10, 10, 60, 30))
    btn._patterns["invoke"] = _FakeInvokePattern(btn)
    root = FakeControl("w", ctype="WindowControl", rect=(0, 0, 800, 600), children=(btn,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()  # 快照期探测 1 次
    before = btn.invoke_probes
    r = b.act(find_el(els, "确定").element_id, action="click", verify_timeout=0.3)
    assert r["success"] is True
    assert btn.invoke_probes - before <= 1  # act 期仅执行取 1 次，无额外探测


def test_p05_b2_classify_new_error_codes():
    """_classify_error_code 识别 pattern_failed/action_ambiguous（先于 action_failed）。"""
    cls = agent_mod.ExecutionAgent._classify_error_code
    assert cls("UIA 操作失败: pattern_failed invoke exec failed: dead") == "pattern_failed"
    assert cls("action_ambiguous: no interactive pattern for edit control") == "action_ambiguous"
    # 含 "failed:" 但命中 pattern_failed 时不得误判为 action_failed（顺序保证）
    assert cls("invoke exec failed: pattern_failed") == "pattern_failed"


def test_p05_b2_agent_propagates_pattern_failed_error_code():
    """agent 层把 pattern_failed + 具体 hint 透传给统一错误契约（不覆盖底层 hint）。"""
    bridge = _BridgeStub(
        {"success": False, "via": None, "error_code": "pattern_failed",
         "error": "invoke exec failed: RuntimeError('dead')",
         "hint": "模式执行失败…禁止重试同一动作补刀——先观察再决策"}
    )
    a = _make_agent_with_fake_bridge(bridge)
    r = a.dispatch_tool("click", {"element_id": "u1", "name": "确定"})
    assert r["ok"] is False
    assert r["error_code"] == "pattern_failed"
    assert "补刀" in r["hint"]  # 底层已带具体 hint，_ERROR_HINTS 通用 hint 不覆盖


# ═══════════════════════════════════════════════════════════════════════════
# P0.5-B3 焦点感知（台账 B3）
# ═══════════════════════════════════════════════════════════════════════════


def _focused_auto(monkeypatch, root, focused):
    """install_fake_uia + 补 GetFocusedControl（B3）。"""
    install_fake_uia(monkeypatch, root)
    sys.modules["uiautomation"].GetFocusedControl = lambda: focused


class _UnavailableBridge(_BridgeStub):
    """available=False 的桥：_do_paste_text 应跳过焦点断言且完全不触碰焦点。"""

    available = False

    def get_focused_now(self):
        raise AssertionError("桥不可用时不应触碰焦点")


def test_p05_b3_snapshot_captures_focused_and_agent_surfaces_it(monkeypatch):
    """① fake auto 带 GetFocusedControl：snapshot 后 last_focused 有值，result['focused'] 正确。"""
    focused = FakeControl("搜索框", ctype="EditControl", rect=(100, 10, 300, 40))
    btn = FakeControl("确定", ctype="ButtonControl", rect=(10, 10, 60, 30))
    btn._patterns["invoke"] = _FakeInvokePattern(btn)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(btn,))
    _focused_auto(monkeypatch, root, focused)

    b = UIABridge()
    els = b.snapshot()
    assert els, "snapshot 应有控件"
    f = b.last_focused()
    assert f is not None
    assert f["name"] == "搜索框"
    assert f["type"] == "edit"
    assert f["class"] == "DummyClass"
    assert f["bbox"] == [100, 10, 300, 40]  # 绝对坐标

    # agent 层：观察结果头部 focused 字段（bbox 转相对窗口同投影口径）
    a = agent_mod.ExecutionAgent()
    a._uia = b
    a.screen_source = "uia"
    r = a._do_get_screen_info()
    assert r["focused"]["name"] == "搜索框"
    assert r["focused"]["type"] == "edit"
    assert r["focused"]["bbox"] == [100, 10, 200, 30]  # [左,上,宽,高] 相对窗口


def test_p05_b3_paste_expect_focus_match_allows_and_pastes(monkeypatch):
    """② expect_focus 匹配（双向包含）→ 放行且粘贴执行。"""
    focused = FakeControl("全局搜索框", ctype="EditControl", rect=(100, 10, 300, 40))
    _focused_auto(monkeypatch, None, focused)
    b = UIABridge()
    a = _make_agent_with_fake_bridge(b)
    pasted = []
    import pyautogui as _pag

    monkeypatch.setattr(_pag, "hotkey", lambda *a, **k: pasted.append(a))
    monkeypatch.setattr(agent_mod.pyperclip, "paste", lambda: "")
    monkeypatch.setattr(agent_mod.pyperclip, "copy", lambda v: None)
    r = a._do_paste_text("你好", expect_focus="搜索框")  # "搜索框" 真含于 "全局搜索框"（双向包含放行）
    assert r["success"] is True
    assert pasted  # ctrl+v 已执行


def test_p05_b3_paste_expect_focus_mismatch_rejects(monkeypatch):
    """③ 不匹配 → focus_mismatch、不粘贴、actual_focus 回报真名。"""
    focused = FakeControl("地址栏", ctype="EditControl", rect=(100, 10, 300, 40))
    _focused_auto(monkeypatch, None, focused)
    b = UIABridge()
    a = _make_agent_with_fake_bridge(b)
    pasted = []
    import pyautogui as _pag

    monkeypatch.setattr(_pag, "hotkey", lambda *a, **k: pasted.append(a))
    monkeypatch.setattr(agent_mod.pyperclip, "paste", lambda: "")
    monkeypatch.setattr(agent_mod.pyperclip, "copy", lambda v: None)
    r = a._do_paste_text("你好", expect_focus="搜索框")
    assert r["success"] is False
    assert r["error_code"] == "focus_mismatch"
    assert "地址栏" in r["error"]
    assert r["actual_focus"]["name"] == "地址栏"
    assert "禁止盲粘" in r["hint"]
    assert pasted == []  # 未下发粘贴


def test_p05_b3_paste_expect_focus_none_focus_conservative_reject(monkeypatch):
    """桥 available 但拿不到焦点（None）→ 保守按不匹配拒发。"""
    _focused_auto(monkeypatch, None, None)  # GetFocusedControl 返回 None
    b = UIABridge()
    a = _make_agent_with_fake_bridge(b)
    pasted = []
    import pyautogui as _pag

    monkeypatch.setattr(_pag, "hotkey", lambda *a, **k: pasted.append(a))
    monkeypatch.setattr(agent_mod.pyperclip, "paste", lambda: "")
    monkeypatch.setattr(agent_mod.pyperclip, "copy", lambda v: None)
    r = a._do_paste_text("你好", expect_focus="搜索框")
    assert r["success"] is False
    assert r["error_code"] == "focus_mismatch"
    assert "未知" in r["error"]
    assert pasted == []


def test_p05_b3_paste_expect_focus_skipped_when_bridge_unavailable(monkeypatch):
    """④ 桥不可用（available False）→ 跳过断言照常粘贴。"""
    bridge = _UnavailableBridge({"success": True})
    a = _make_agent_with_fake_bridge(bridge)
    pasted = []
    import pyautogui as _pag

    monkeypatch.setattr(_pag, "hotkey", lambda *a, **k: pasted.append(a))
    monkeypatch.setattr(agent_mod.pyperclip, "paste", lambda: "")
    monkeypatch.setattr(agent_mod.pyperclip, "copy", lambda v: None)
    r = a._do_paste_text("你好", expect_focus="搜索框")
    assert r["success"] is True
    assert pasted


def test_p05_b3_paste_schema_has_expect_focus_and_dispatch_forwards(monkeypatch):
    """paste_text schema 增 expect_focus（可选）；dispatch 透传。"""
    a = agent_mod.ExecutionAgent()
    tools = {t["function"]["name"]: t["function"] for t in a.tools}
    fn = tools["paste_text"]
    assert "expect_focus" in fn["parameters"]["properties"]
    assert "expect_focus" not in fn["parameters"]["required"]
    # dispatch 透传
    bridge = _UnavailableBridge({"success": True})
    a2 = _make_agent_with_fake_bridge(bridge)
    monkeypatch.setattr(a2, "_do_paste_text", lambda *args, **kw: {"seen": kw})
    r = a2.dispatch_tool("paste_text", {"text": "x", "expect_focus": "搜索框"})
    assert r["seen"]["expect_focus"] == "搜索框"
    # 错误分类：focus_mismatch 先于 action_failed
    cls = agent_mod.ExecutionAgent._classify_error_code
    assert cls("UIA 操作失败: focus_mismatch") == "focus_mismatch"
    assert cls("focus_mismatch: 粘贴已拒绝") == "focus_mismatch"
    # 契约 hint 存在
    assert "禁止盲粘" in agent_mod.ExecutionAgent._ERROR_HINTS["focus_mismatch"]


# ═══════════════════════════════════════════════════════════════════════════
# P0.5-B4 动作四件套（台账 B4：WindowPattern 组/select_menu_path/set_range/right_click）
# ═══════════════════════════════════════════════════════════════════════════


def _capture_clicker(monkeypatch):
    """拦截 clicker.click_at（_act_coord 运行时按模块属性取函数）。"""
    import server.services.executor.clicker as clicker_mod

    calls = []

    def _fake(pt, button="left", clicks=1):
        calls.append({"pt": pt, "button": button, "clicks": clicks})
        return {"success": True, "x": pt[0], "y": pt[1], "button": button, "clicks": clicks}

    monkeypatch.setattr(clicker_mod, "click_at", _fake)
    return calls


def test_p05_b4_right_click_coord_event_and_actionability_gate(monkeypatch):
    """① right_click 走 click_at(button="right") 像素事件；disabled 控件被预检拒。"""
    btn = FakeControl("文件", ctype="MenuItemControl", rect=(10, 10, 60, 30))
    # 故意给 invoke：右键不得因决策表而改走 pattern（像素事件语义）
    btn._patterns["invoke"] = _FakeInvokePattern(btn)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(btn,))
    install_fake_uia(monkeypatch, root)
    calls = _capture_clicker(monkeypatch)

    b = UIABridge()
    els = b.snapshot()
    eid = find_el(els, "文件").element_id
    r = b.act(eid, action="right_click", action_timeout=0.2, verify_timeout=0.1)
    assert r["success"] is True
    assert calls and calls[-1]["button"] == "right" and calls[-1]["clicks"] == 1
    assert btn.log == []  # 未走 Invoke pattern

    disabled = FakeControl("灰条", ctype="MenuItemControl", rect=(10, 40, 60, 60), enabled=False)
    root2 = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(disabled,))
    install_fake_uia(monkeypatch, root2)
    b2 = UIABridge()
    els2 = b2.snapshot()
    eid2 = find_el(els2, "灰条").element_id
    r2 = b2.act(eid2, action="right_click", action_timeout=0.2, verify_timeout=0.1)
    assert r2["success"] is False
    assert r2["error_code"] == "not_actionable"
    assert "enabled" in r2["missing_predicates"]


def test_p05_b4_set_range_success_and_no_range_pattern_failclosed(monkeypatch):
    """② set_range 成功→props diff 含 range；无 rangevalue→no_range_pattern 且未执行。"""
    slider = FakeControl("音量", ctype="SliderControl", rect=(10, 10, 210, 30))
    slider._patterns["rangevalue"] = _FakeRangeValuePattern(slider, initial=10.0)
    plain = FakeControl("确定", ctype="ButtonControl", rect=(10, 50, 60, 70))
    plain._patterns["invoke"] = _FakeInvokePattern(plain)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(slider, plain))
    root._patterns["window"] = _FakeWindowPattern(root)
    install_fake_uia(monkeypatch, root)

    b = UIABridge()
    els = b.snapshot()
    eid = find_el(els, "音量").element_id
    r = b.act(eid, action="set_range", value=55.5, action_timeout=0.2, verify_timeout=0.1)
    assert r["success"] is True
    assert r["via"] == "uia_setrange"
    assert slider._range_value == 55.5
    diff = r["prop_diff"]
    assert "range" in diff["changed"]
    assert diff["before"]["range"] == 10.0 and diff["after"]["range"] == 55.5
    assert r["state_changed"] is True

    eid2 = find_el(els, "确定").element_id
    r2 = b.act(eid2, action="set_range", value=1, action_timeout=0.2, verify_timeout=0.1)
    assert r2["success"] is False
    assert r2["error_code"] == "no_range_pattern"
    assert plain.log == []  # 未执行任何模式
    assert "press_key" in r2["hint"]

    # WindowPattern/rangevalue 已入探测表（投影可见）
    proj_names = {p["name"]: p["patterns"] for p in b.last_projection()}
    assert "rangevalue" in proj_names["音量"]
    assert "window" in proj_names["窗口"]


def test_p05_b4_select_menu_path_two_levels(monkeypatch):
    """③ 两级：expand 头→重扫→末项 invoke；path_trace 对。"""
    leaf = FakeControl("保存", ctype="MenuItemControl", rect=(10, 60, 60, 80))
    leaf._patterns["invoke"] = _FakeInvokePattern(leaf)
    header = FakeControl("文件", ctype="MenuItemControl", rect=(10, 10, 60, 30))
    header._patterns["expand"] = _FakeExpandPattern(header, children=[leaf])
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(header,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    a = _make_agent_with_fake_bridge(b)

    r = a._do_select_menu_path(["文件", "保存"])
    assert r["success"] is True
    assert [t["action"] for t in r["path_trace"]] == ["expand", "click"]
    assert [t["item"] for t in r["path_trace"]] == ["文件", "保存"]
    assert all(t["ok"] for t in r["path_trace"])
    assert header.log == ["expand"]
    assert "invoke" in leaf.log
    assert r["ids_refreshed"] is True
    assert r["new_elements"]  # 末次投影 top-N


def test_p05_b4_select_menu_path_mid_level_missing_reports_visible(monkeypatch):
    """④ 中途缺失→menu_path_not_found + visible_at_level + 末项未执行。"""
    leaf = FakeControl("保存", ctype="MenuItemControl", rect=(10, 60, 60, 80))
    leaf._patterns["invoke"] = _FakeInvokePattern(leaf)
    header = FakeControl("文件", ctype="MenuItemControl", rect=(10, 10, 60, 30))
    header._patterns["expand"] = _FakeExpandPattern(header, children=[leaf])
    other = FakeControl("编辑", ctype="MenuItemControl", rect=(70, 10, 120, 30))
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(header, other))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    a = _make_agent_with_fake_bridge(b)

    r = a._do_select_menu_path(["文件", "打印", "不存在项"])
    assert r["success"] is False
    assert r["error_code"] == "menu_path_not_found"
    assert r["failed_at"] == 1 and r["wanted"] == "打印"
    vis = r["visible_at_level"]
    assert "保存" in vis and "编辑" in vis and "打印" not in vis  # 该层实际可见项清单
    assert len(r["path_trace"]) == 1  # 第一级 expand 成功
    assert leaf.log == []  # 末项未执行


def test_p05_b4_window_action_activate_close_and_not_found(monkeypatch):
    """⑤ activate/close 日志断言；title 无匹配→window_not_found；element_id 解析顶层。"""
    win = FakeControl("无标题 - 记事本", ctype="WindowControl", rect=(0, 0, 800, 600))
    btn = FakeControl("保存", ctype="ButtonControl", rect=(10, 10, 60, 30))
    win._children = [btn]
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(btn,))
    install_fake_uia(monkeypatch, root, roots=[win])
    b = UIABridge()
    a = _make_agent_with_fake_bridge(b)

    r = a._do_window_action("activate", title="记事本")
    assert r["success"] is True and "focus" in win.log
    assert r["via"] == "uia_window"

    r2 = a._do_window_action("close", title="记事本")
    assert r2["success"] is True and "close" in win.log

    r3 = a._do_window_action("minimize", title="不存在的窗口X")
    assert r3["success"] is False and r3["error_code"] == "window_not_found"

    # element_id → GetTopLevelControl 解析
    b.snapshot()
    eid = find_el(b.snapshot(), "保存").element_id
    btn._top_level = win
    r4 = a._do_window_action("restore", title="", element_id=eid)
    assert r4["success"] is True and "restore" in win.log


def test_p05_b4_four_tools_dispatch_record_evidence_and_errors(monkeypatch):
    """⑥ 四工具 dispatch 后 _action_evidence 有账本条目；错误码分类/提示齐。"""
    slider = FakeControl("音量", ctype="SliderControl", rect=(10, 10, 210, 30))
    slider._patterns["rangevalue"] = _FakeRangeValuePattern(slider)
    leaf = FakeControl("保存", ctype="MenuItemControl", rect=(10, 60, 60, 80))
    leaf._patterns["invoke"] = _FakeInvokePattern(leaf)
    header = FakeControl("文件", ctype="MenuItemControl", rect=(10, 10, 60, 30))
    header._patterns["expand"] = _FakeExpandPattern(header, children=[leaf])
    win = FakeControl("记事本窗口", ctype="WindowControl", rect=(0, 0, 800, 600))
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600), children=(slider, header))
    root._top_level = win
    install_fake_uia(monkeypatch, root, roots=[win])
    _capture_clicker(monkeypatch)
    b = UIABridge()
    a = _make_agent_with_fake_bridge(b)
    a._reset_step_ledger()
    els = a._do_get_screen_info()
    ids = {e["name"]: e["id"] for e in els["elements"]}

    assert a.dispatch_tool("right_click", {"element_id": ids["音量"], "name": "音量"})["ok"] is True
    assert a.dispatch_tool("set_range", {"element_id": ids["音量"], "name": "音量", "value": 66})["ok"] is True
    assert a.dispatch_tool("select_menu_path", {"items": ["文件", "保存"]})["ok"] is True
    els2 = a._do_get_screen_info()
    ids2 = {e["name"]: e["id"] for e in els2["elements"]}
    assert a.dispatch_tool("window_action", {"op": "activate", "title": "", "element_id": ids2["音量"]})["ok"] is True

    tools = [e["tool"] for e in a._action_evidence]
    assert tools == ["right_click", "set_range", "select_menu_path", "window_action"]

    cls = agent_mod.ExecutionAgent._classify_error_code
    assert cls("menu_path_not_found: 菜单第 2 级未找到") == "menu_path_not_found"
    assert cls("no window matched: window_not_found") == "window_not_found"
    assert cls("control does not support RangeValuePattern: no_range_pattern") == "no_range_pattern"
    hints = agent_mod.ExecutionAgent._ERROR_HINTS
    for code in ("menu_path_not_found", "window_not_found", "no_range_pattern"):
        assert hints[code]

    # schema 四工具齐 + 可选参数口径
    tfns = {t["function"]["name"]: t["function"] for t in agent_mod.ExecutionAgent().tools}
    assert tfns["set_range"]["parameters"]["required"] == ["element_id", "name", "value"]
    assert tfns["window_action"]["parameters"]["properties"]["op"]["enum"] == [
        "activate", "minimize", "maximize", "restore", "close"
    ]
    assert tfns["select_menu_path"]["parameters"]["required"] == ["items"]


# ═══════════════════════════════════════════════════════════════════════════
# P0.5-B1 投机批量动作 perform_batch（台账 B1：UFO² Algorithm 1 的 L5 翻译版）
# 契约：≤8 个决策互不依赖的元素动作；首败即停；未执行项显式回报；
# 子动作逐个进 _LoopDetector 滑窗与证据账本；ids_refreshed 触发正常截断。
# ═══════════════════════════════════════════════════════════════════════════

_B1_TYPE_OK = {
    "success": True, "via": "uia_value", "action_ok": True,
    "verified": True, "state_changed": True,
}


class _SeqActBridge(_BridgeStub):
    """按 act 调用次序回放预置结果的桩（首败即停/重观察截断场景用）。"""

    def __init__(self, results):
        super().__init__({})
        self._results = list(results)

    def act(self, element_id, action="click", text=None, expect=None, **kw):
        self.calls.append(("act", element_id, action, expect))
        self.calls_kw.append(kw)
        idx = sum(1 for c in self.calls if c[0] == "act") - 1
        return dict(self._results[min(idx, len(self._results) - 1)])


def _b1_form_agent(bridge):
    """三个互不影响的输入字段（姓名/邮箱/电话）的表单场景 agent。"""
    a = _make_agent_with_fake_bridge(bridge)
    a.element_map = {
        eid: UIElement(
            element_id=eid, bbox=[10, 10 + i * 40, 120, 30], element_type="input",
            text=nm, confidence=0.9, center=[70, 25 + i * 40],
        )
        for i, (eid, nm) in enumerate((("u1", "姓名"), ("u2", "邮箱"), ("u3", "电话")))
    }
    return a


def _b1_fill(eid, nm, txt):
    return {"tool": "type_text", "element_id": eid, "name": nm, "text": txt}


def test_p05_b1_batch_all_success_three_type_text():
    """① 三个互不影响字段连填：全成，ok True，逐项下发、逐项进证据账本。"""
    bridge = _BridgeStub(_B1_TYPE_OK)
    a = _b1_form_agent(bridge)
    r = a.dispatch_tool("perform_batch", {"actions": [
        _b1_fill("u1", "姓名", "张三"),
        _b1_fill("u2", "邮箱", "a@b.c"),
        _b1_fill("u3", "电话", "138"),
    ]})
    assert r["ok"] is True and r["success"] is True
    assert r["partial"] is False and r["failed_at"] is None
    assert r["truncated_by_reobserve"] is False and r["not_executed"] == []
    acts = [c for c in bridge.calls if c[0] == "act"]
    assert len(acts) == 3  # 子动作逐个真实下发（复用 _do_* 全套链路）
    assert [e["index"] for e in r["completed"]] == [0, 1, 2]
    assert [e["tool"] for e in r["completed"]] == ["type_text"] * 3
    assert all(e["action_summary"] for e in r["completed"])
    # 证据账本按子工具名记账；perform_batch 不入 _MUTATING_TOOLS、不重复记
    assert "perform_batch" not in agent_mod.ExecutionAgent._MUTATING_TOOLS
    assert [e["tool"] for e in a._action_evidence] == ["type_text"] * 3


def test_p05_b1_batch_first_fail_stops_and_reports_not_executed(monkeypatch):
    """② 第 2 项失败：首败即停，第 3 项不下发、显式回报，顶层透传子错误码。"""
    bridge = _SeqActBridge([
        _B1_TYPE_OK,
        {"success": False, "via": "uia_value", "action_ok": False,
         "error": "ValuePattern.SetValue 执行失败（fail-closed）: pattern_failed",
         "error_code": "pattern_failed"},
        _B1_TYPE_OK,  # 不应到达
    ])
    a = _b1_form_agent(bridge)
    monkeypatch.setattr(
        a, "_do_get_screen_info",
        lambda: {"success": True, "elements": [{"id": "n1", "name": "姓名"}]},
    )
    r = a.dispatch_tool("perform_batch", {"actions": [
        _b1_fill("u1", "姓名", "张三"),
        _b1_fill("u2", "邮箱", "a@b.c"),
        _b1_fill("u3", "电话", "138"),
    ]})
    assert r["ok"] is False and r["success"] is False
    acts = [c for c in bridge.calls if c[0] == "act"]
    assert len(acts) == 2  # 第 3 项未下发
    assert r["failed_at"] == 1 and r["failure"]["tool"] == "type_text"
    assert r["error_code"] == "pattern_failed"  # 顶层透传首个失败子码
    assert r["failure"]["error_code"] == "pattern_failed"
    assert r["not_executed"] == [
        {"index": 2, "tool": "type_text", "error": "Not executed: earlier action failed"}
    ]
    assert len(r["completed"]) == 1 and r["partial"] is True
    assert "补刀" in (r["hint"] or "")  # 子动作自纠 hint 透传
    assert "剩余 1 项未执行" in r["hint"]
    assert r["new_elements"] == [{"id": "n1", "name": "姓名"}]  # 失败时附最新观察


def test_p05_b1_batch_illegal_tool_rejects_whole_batch_zero_exec():
    """③ 白名单外子项（get_screen_info/嵌套/控制类）→ batch_invalid 整批拒收、零执行。"""
    bridge = _BridgeStub(_B1_TYPE_OK)
    a = _b1_form_agent(bridge)
    r = a.dispatch_tool("perform_batch", {"actions": [
        _b1_fill("u1", "姓名", "x"),  # 合法首项也不得执行
        {"tool": "get_screen_info"},
    ]})
    assert r["ok"] is False and r["error_code"] == "batch_invalid"
    assert bridge.calls == []  # 零执行（预校验在首个 dispatch 之前）
    assert r["completed"] == [] and r["not_executed"] == []
    for t in agent_mod._BATCH_ALLOWED_TOOLS:
        assert t in r["hint"]  # hint 列出允许集
    for bad in ("perform_batch", "mark_step_done", "mark_step_failed", "report_infeasible",
                "ask_user", "launch_app", "select_menu_path", "window_action", "browser_click"):
        r2 = a._do_perform_batch([_b1_fill("u1", "姓名", "x"), {"tool": bad}])
        assert r2["success"] is False and r2["error_code"] == "batch_invalid", bad
    assert a._do_perform_batch([])["error_code"] == "batch_invalid"  # 空数组拒收
    assert a._do_perform_batch("not-a-list")["error_code"] == "batch_invalid"
    assert bridge.calls == []


def test_p05_b1_batch_over_max_rejects_zero_exec():
    """④ 9 项超限 → batch_invalid 零执行；8 项（上限值）合法放行。"""
    bridge = _BridgeStub(_B1_TYPE_OK)
    a = _b1_form_agent(bridge)
    nine = [_b1_fill("u1", "姓名", f"t{i}") for i in range(9)]
    r = a.dispatch_tool("perform_batch", {"actions": nine})
    assert r["ok"] is False and r["error_code"] == "batch_invalid"
    assert "9" in r["error"] and bridge.calls == []
    r2 = a.dispatch_tool("perform_batch", {"actions": nine[:8]})
    assert r2["ok"] is True and len(r2["completed"]) == 8
    acts = [c for c in bridge.calls if c[0] == "act"]
    assert len(acts) == 8


def test_p05_b1_batch_truncated_by_reobserve_keeps_rest_unexecuted(monkeypatch):
    """⑤ 子动作 ok 但触发自动重观察（ids_refreshed）→ 批次正常截断，剩余作废。"""
    bridge = _SeqActBridge([
        {"success": True, "via": "uia_value", "action_ok": True,
         "verified": False, "verify_reason": "control gone", "state_changed": False},
        _B1_TYPE_OK,  # 不应到达（旧 id 已作废）
    ])
    a = _b1_form_agent(bridge)
    fresh = [{"id": "n1", "name": "新弹层"}]
    monkeypatch.setattr(
        a, "_do_get_screen_info", lambda: {"success": True, "elements": fresh}
    )
    r = a.dispatch_tool("perform_batch", {"actions": [
        _b1_fill("u1", "姓名", "张三"),
        _b1_fill("u2", "邮箱", "a@b.c"),
        {"tool": "press_key", "keys": "enter"},
    ]})
    acts = [c for c in bridge.calls if c[0] == "act"]
    assert len(acts) == 1  # 截断后不得再用作废 id 下发
    assert r["ok"] is True  # 已执行项全成 → 批次本身成功（正常截断非失败）
    assert r["truncated_by_reobserve"] is True and r["failed_at"] is None
    assert r["partial"] is True and len(r["completed"]) == 1
    assert [e["index"] for e in r["not_executed"]] == [1, 2]
    assert all("re-observation" in e["error"] for e in r["not_executed"])
    assert r["new_elements"] == fresh  # 附最新观察
    assert "new_elements" in r["hint"] and "重新编排" in r["hint"]


def test_p05_b1_batch_subactions_flow_into_loop_detector_window():
    """⑥ 滑窗记账：1 批 5 个相同 click 子动作逐个进滑窗（第 5 项时 repeat_count>=5 可观测、
    nudge 出「同一动作」文案）；整批哈希批后再记一次（整批重复可抓）。"""
    bridge = _click_ok_bridge()
    a = _b1_form_agent(bridge)
    ld = agent_mod._LoopDetector()
    seen = []
    orig = ld.record_action

    def _spy(tool, args, ok):
        orig(tool, args, ok)
        seen.append((tool, ld.repeat_count(), ld.build_nudge()))

    ld.record_action = _spy  # 实例级探针：观测每条记账时刻的滑窗状态
    a._loop_detector = ld
    batch5 = [{"tool": "click", "element_id": "u1", "name": "姓名"}] * 5
    r = a._do_perform_batch(batch5)
    assert r["success"] is True and len(r["completed"]) == 5
    # 第 5 个子动作记账时刻：尾部相同动作连击 5 → 阈值越界 + 「同一动作」纠偏文案
    assert max(n for _, n, _ in seen) >= 5
    assert any("同一动作" in msg for _, _, msg in seen)
    click_key = ld.action_key("click", {"element_id": "u1", "name": "姓名"})
    batch_key = ld.action_key("perform_batch", {"actions": batch5})
    recent = list(ld._recent)
    assert recent.count(click_key) == 5  # 逐子动作进滑窗（台账硬要求）
    assert recent[-1] == batch_key and recent.count(batch_key) == 1  # 整批哈希一次
    # 重复整批：batch 哈希逐批累积，滑窗内可抓「同样的 8 连击被反复编排」
    for _ in range(3):
        assert a._do_perform_batch(batch5)["success"] is True
    assert list(ld._recent).count(batch_key) == 4
    # execute_step 顶层对同载荷再记一次 perform_batch → 同哈希双重覆盖无害（尾部连击数 +1）
    before = ld.repeat_count()
    ld.record_action("perform_batch", {"actions": batch5}, True)
    assert ld.repeat_count() == before + 1


def test_p05_b1_batch_evidence_feeds_done_gate(monkeypatch):
    """⑦ done gate 兼容：批量子动作的 state_changed 进证据账本，批量后 mark_step_done 一次过、
    不带 unverified_done；同时验证 execute_step 已暴露 self._loop_detector。"""
    bridge = _BridgeStub(_B1_TYPE_OK)
    a = _scripted_agent(monkeypatch, [
        ("perform_batch", {"actions": [
            _b1_fill("u1", "姓名", "张三"),
            _b1_fill("u2", "邮箱", "a@b.c"),
            _b1_fill("u3", "电话", "138"),
        ]}),
        ("mark_step_done", {"reason": "三个字段已填", "evidence": ""}),
    ], bridge=bridge)
    a.element_map = _b1_form_agent(bridge).element_map
    result = a.execute_step(_step("填写表单三个字段"), goal="g", previous_steps=[])
    assert result.status == "done"
    assert "unverified_done" not in (result.evidence or "")
    assert "type_text→u1" in (result.evidence or "")  # 强证据取自子动作账本
    assert getattr(a, "_loop_detector", None) is not None  # B1 接线：滑窗暴露给批量
    acts = [c for c in bridge.calls if c[0] == "act"]
    assert len(acts) == 3  # 批量在 execute_step 真实链路里也逐项下发


def test_p05_b1_batch_schema_and_prompt_wiring():
    """⑧ schema 形状与 prompt 接线：工具数钉 18/26、maxItems/enum/required、纪律文案。"""
    tfns = {t["function"]["name"]: t["function"] for t in agent_mod._build_tool_definitions()}
    assert len(tfns) == 26  # 25 → 26（test_pure_functions 双钉同步 18/26）
    desktop = [n for n in tfns if not n.startswith("browser_")]
    assert len(desktop) == 18 and "perform_batch" in desktop
    p = tfns["perform_batch"]["parameters"]
    assert p["required"] == ["actions"]
    arr = p["properties"]["actions"]
    assert arr["type"] == "array"
    assert arr["maxItems"] == agent_mod._BATCH_MAX_ACTIONS == 8  # schema 与代码同源
    item = arr["items"]
    assert item["required"] == ["tool"]
    assert item["properties"]["tool"]["enum"] == list(agent_mod._BATCH_ALLOWED_TOOLS)
    for excluded in ("get_screen_info", "mark_step_done", "mark_step_failed",
                     "report_infeasible", "ask_user", "launch_app",
                     "select_menu_path", "window_action", "perform_batch"):
        assert excluded not in item["properties"]["tool"]["enum"]
    # 顶层描述写清使用时机纪律
    desc = tfns["perform_batch"]["description"]
    assert "仅当后续动作不依赖前面动作的结果时使用" in desc
    assert "需要观察后决策的放主循环" in desc
    # prompt：可用工具行 + 效率约束句
    assert "- perform_batch(actions): 批量执行最多8个互不依赖的元素动作" in agent_mod.EXECUTION_SYSTEM_PROMPT
    assert "填表类连续同构动作" in agent_mod.EXECUTION_SYSTEM_PROMPT


def test_p05_b1_batch_redline_and_name_guard_apply_per_subaction(monkeypatch):
    """⑨ 红线与 id×name 交叉验证逐个生效：批量不旁路任何单动作检查。"""
    bridge = _click_ok_bridge()
    a = _b1_form_agent(bridge)
    # name 交叉验证不符 → 该项拒发（零 act 下发）、首败即停、错误码透传
    r = a.dispatch_tool("perform_batch", {"actions": [
        {"tool": "click", "element_id": "u1", "name": "取消"},
        {"tool": "click", "element_id": "u1", "name": "姓名"},
    ]})
    assert r["ok"] is False and r["error_code"] == "name_mismatch"
    assert bridge.calls == []  # NAME_MISMATCH 在 act 之前拦截
    assert r["failed_at"] == 0 and r["completed"] == []
    assert len(r["not_executed"]) == 1
    assert r["failure"]["error_code"] == "name_mismatch"
    # 红线（黄区）同样在子动作内部拦：dispatch 不旁路 check_step
    def _yellow(step_text):
        class _S:
            level = "yellow"
            reason = "疑似发送"
        return _S()

    monkeypatch.setattr(agent_mod, "check_step", _yellow)
    r2 = a.dispatch_tool("perform_batch", {"actions": [
        {"tool": "click", "element_id": "u1", "name": "姓名"},
    ]})
    assert r2["ok"] is False and r2["error_code"] == "confirm_required"
    assert r2["failed_at"] == 0 and bridge.calls == []


# ═══════════════════════════════════════════════════════════════════════════
# P0.5-A4 稳定 id + element_stale 协议（台账 A4）
# eid = e<sha1(hwnd/ProcessId + runtime-id)[:10]>；句柄表跨快照存活；
# 控件销毁 → act/verify 报 element_stale（不落坐标）；clear()（换步）才全废。
# ═══════════════════════════════════════════════════════════════════════════

import re as _re  # noqa: E402


class _RuntimeIdControl(FakeControl):
    """带 GetRuntimeId 的假控件（A4 稳定 id 路径；基类默认无 → 回退 u{n}）。"""

    def __init__(self, *a, runtime_id=(4, 100), **k):
        super().__init__(*a, **k)
        self._rid = list(runtime_id)

    def GetRuntimeId(self):
        return list(self._rid)


class _DestroyedControl(FakeControl):
    """A4 销毁模拟：dead=True 后属性读取抛异常（COMError/ElementNotAvailable 语义）。"""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._destroyed = False

    @property
    def Name(self):  # noqa: N802 —— 覆盖基类实例属性，模拟销毁后属性读取抛
        if self._destroyed:
            raise RuntimeError("ElementNotAvailable: control destroyed")
        return self._name

    @Name.setter
    def Name(self, v):
        self._name = v

    def destroy(self):
        self._destroyed = True


def _a4_tree():
    a = _RuntimeIdControl("甲按钮", ctype="ButtonControl", rect=(10, 10, 60, 30),
                          runtime_id=(4, 100))
    a._patterns["invoke"] = _FakeInvokePattern(a)
    b = _RuntimeIdControl("乙输入", ctype="EditControl", rect=(10, 50, 200, 80),
                          runtime_id=(4, 200))
    b._patterns["value"] = _FakeValuePattern(b)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600),
                       children=(a, b))
    return root, a, b


def test_p05_a4_stable_eid_identical_across_snapshots(monkeypatch):
    """同一控件两次 snapshot → eid 相同，形状 e<10hex>（A4 核心契约）。"""
    root, a_btn, _ = _a4_tree()
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    e1 = find_el(b.snapshot(), "甲按钮").element_id
    e2 = find_el(b.snapshot(), "甲按钮").element_id
    assert e1 == e2
    assert _re.fullmatch(r"e[0-9a-f]{10}", e1)
    # 不同控件 → 不同 eid
    e3 = find_el(b.snapshot(), "乙输入").element_id
    assert e3 != e1


def test_p05_a4_fallback_u_n_without_runtime_id(monkeypatch):
    """GetRuntimeId 缺失的烂控件 → 回退现场序 u{n} 且仍可 act（兼容旧形状）。"""
    btn = FakeControl("确定", ctype="ButtonControl", rect=(10, 10, 60, 30))
    btn._patterns["invoke"] = _FakeInvokePattern(btn)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600),
                       children=(btn,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    eid = find_el(b.snapshot(), "确定").element_id
    assert _re.fullmatch(r"u\d+", eid)
    r = b.act(eid, action="click", verify_timeout=0.2)
    assert r["success"] is True and "invoke" in btn.log


def test_p05_a4_collision_same_traversal_appends_number(monkeypatch):
    """同一次观察内两个控件算出同一 base eid → 第二个追加 #2（防互相覆盖）。"""
    c1 = _RuntimeIdControl("一", ctype="ButtonControl", rect=(0, 0, 50, 20),
                           runtime_id=(7, 7))
    c1._patterns["invoke"] = _FakeInvokePattern(c1)
    c2 = _RuntimeIdControl("二", ctype="ButtonControl", rect=(0, 30, 50, 50),
                           runtime_id=(7, 7))
    c2._patterns["invoke"] = _FakeInvokePattern(c2)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600),
                       children=(c1, c2))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    ids = sorted(e.element_id for e in els)
    assert len(set(ids)) == 2  # 没有互相覆盖
    assert any(_re.fullmatch(r"e[0-9a-f]{10}#\d+", i) for i in ids)


def test_p05_a4_destroyed_control_act_stale_no_coord(monkeypatch):
    """句柄死亡 → act 报 element_stale（先于 pattern/actionability 判定）且不落坐标。"""
    calls = _capture_clicker(monkeypatch)
    btn = _DestroyedControl("确定", ctype="ButtonControl", rect=(10, 10, 60, 30))
    btn._patterns["invoke"] = _FakeInvokePattern(btn)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600),
                       children=(btn,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    eid = find_el(b.snapshot(), "确定").element_id
    btn.destroy()
    r = b.act(eid, action="click", action_timeout=0.2)
    assert r["success"] is False
    assert r["error_code"] == "element_stale"
    assert r["action_ok"] is False and r["via"] is None
    assert "重新观察" in r["hint"]
    assert calls == []  # 绝不落坐标
    v = b.verify(eid, timeout=0.2)
    assert v["success"] is False and "stale" in v["reason"]


def test_p05_a4_clear_invalidates_all_ids(monkeypatch):
    """换步 clear() → 稳定 id 也全废：act 回到旧 element_not_found 语义。"""
    root, *_ = _a4_tree()
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    eid = find_el(b.snapshot(), "甲按钮").element_id
    b.clear()
    r = b.act(eid, action="click")
    assert r["success"] is False
    assert "not found" in r["error"]  # 从未见过/已作废 → 旧语义不变
    assert r.get("error_code") is None


def test_p05_a4_surviving_handle_actable_when_absent_from_view(monkeypatch):
    """控件存活但掉出当次视图（树重排后不再被观察）→ 旧 id 仍可按句柄 act。"""
    root, a_btn, b_edit = _a4_tree()
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    edit_eid = find_el(els, "乙输入").element_id
    # 乙控件从树上移除（对象仍存活），重新观察
    root._children = [a_btn]
    b.snapshot()
    assert edit_eid not in b._last_controls  # 不在当次视图
    r = b.act(edit_eid, action="type", text="hi")  # 但句柄存活
    assert r["success"] is True
    assert ("setvalue", "hi") in b_edit.log


def test_p05_a4_agent_element_map_survives_observation(monkeypatch):
    """agent 侧：新一次观察不使存活控件旧 id 出局（element_map=跨快照缓存）。"""
    root, a_btn, b_edit = _a4_tree()
    install_fake_uia(monkeypatch, root)
    a = agent_mod.ExecutionAgent()
    obs = a._do_get_screen_info()
    ids_v1 = {e["id"] for e in obs["elements"]}
    root._children = [a_btn]  # 乙控件掉出树（对象未死）
    obs2 = a._do_get_screen_info()
    ids_v2 = {e["id"] for e in obs2["elements"]}
    # 稳定 id 跨观察一致
    assert ids_v2 & ids_v1  # 甲的 id 两次的投影里相同
    gone = (ids_v1 - ids_v2).pop()
    assert gone in a.element_map  # 但句柄缓存仍认识它（可 act，死了才报 stale）


def test_p05_a4_agent_error_contract_wiring():
    """element_stale 进分类器与默认 hint；'失效' 文案手术完整（prompt 无旧协议残留）。"""
    cls = agent_mod.ExecutionAgent._classify_error_code
    assert cls("uia element 'e012345678' is stale (control destroyed)") == "element_stale"
    assert cls("UIA 操作失败: uia element 'x' is stale") == "element_stale"
    assert agent_mod.ExecutionAgent._ERROR_HINTS["element_stale"]
    prompt = agent_mod.EXECUTION_SYSTEM_PROMPT
    assert "全部失效" not in prompt  # 旧"全部失效"条款清零
    assert "element_stale" in prompt  # 新协议已入 prompt
    gsi = next(t for t in agent_mod.ExecutionAgent().tools
               if t["function"]["name"] == "get_screen_info")
    assert "全部失效" not in gsi["function"]["description"]  # schema 文案同步手术


def test_p05_a4_agent_propagates_element_stale(monkeypatch):
    """agent 层把桥的 element_stale + 具体 hint 透传进统一错误契约。"""
    bridge = _BridgeStub(
        {"success": False, "via": None, "action_ok": False,
         "error_code": "element_stale",
         "error": "uia element 'e123' is stale (control destroyed or UI repainted)",
         "hint": "控件已销毁或界面已重绘，get_screen_info 重新观察后选新 id；不要重试旧 id"}
    )
    a = _make_agent_with_fake_bridge(bridge)
    r = a.dispatch_tool("click", {"element_id": "u1", "name": "确定"})
    assert r["ok"] is False
    assert r["error_code"] == "element_stale"
    assert "不要重试旧 id" in r["hint"]


# ═══════════════════════════════════════════════════════════════════════════
# P0.5-A3 浅探大纲 + scope/filter 下钻 + 词法语义过滤（台账 A3）
# 默认 snapshot(depth 3) 把折叠容器暴露成大纲条目（items/expandable）；
# drill(scope) 加法深扫；词法相关度权重 8 高于 patterns 的 4。
# ═══════════════════════════════════════════════════════════════════════════


def _a3_deep_tree():
    """深度账：root d0 → shallow d1（可见）；c1 d1 → c2 d2 → 折叠容器 d3
    （稳定大纲，deep d4 不可见）+ 烂容器 d3（无 rid → o{n} 临时大纲，
    藏按钮 d4 不可见）。"""
    shallow = _RuntimeIdControl("浅层按钮", ctype="ButtonControl",
                                rect=(10, 10, 70, 34), runtime_id=(1, 11))
    shallow._patterns["invoke"] = _FakeInvokePattern(shallow)
    deep = _RuntimeIdControl("深层按钮", ctype="ButtonControl",
                             rect=(10, 310, 70, 330), runtime_id=(1, 44))
    deep._patterns["invoke"] = _FakeInvokePattern(deep)
    fold = _RuntimeIdControl("折叠容器", ctype="PaneControl",
                             rect=(5, 305, 200, 340), runtime_id=(1, 43),
                             children=(deep,))
    junk = FakeControl("烂容器", ctype="PaneControl", rect=(410, 300, 500, 340),
                       children=(FakeControl("藏按钮", ctype="ButtonControl",
                                             rect=(415, 310, 460, 330)),))
    c2 = _RuntimeIdControl("二级容器", ctype="PaneControl",
                           rect=(5, 300, 400, 345), runtime_id=(1, 42),
                           children=(fold, junk))
    c1 = _RuntimeIdControl("一级容器", ctype="PaneControl",
                           rect=(0, 290, 790, 590), runtime_id=(1, 41),
                           children=(c2,))
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600),
                       children=(shallow, c1))
    return root, shallow, deep, c2


def test_p05_a3_default_shallow_emits_outline_entries(monkeypatch):
    """深树默认观察：折叠容器进大纲（稳定 id 可解析），烂容器给 o{n}，
    深层控件不可见也不可 act；o{n} 不进句柄表。"""
    root, *_ = _a3_deep_tree()
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    assert {e.text for e in els} == {"浅层按钮"}  # depth 3 外的深层按钮不可见
    proj = b.last_projection()
    oc = next(p for p in proj if p["name"] == "折叠容器")
    assert oc["expandable"] is True and oc["items"] == 1
    assert oc["type"] == "pane" and oc["patterns"] == []
    assert _re.fullmatch(r"e[0-9a-f]{10}", oc["id"])
    assert b.has_handle(oc["id"])  # 稳定大纲 id 可 drill
    oh = next(p for p in proj if p["name"] == "烂容器")
    assert oh["id"].startswith("o") and oh["expandable"] is True
    assert not b.has_handle(oh["id"])  # 大纲临时 id 不进句柄表（防对折叠容器开枪）
    # 大纲按 DFS 原位排布：折叠容器 seq 介于浅层按钮与…（seq 单调）
    seqs = [p["seq"] for p in proj]
    assert seqs == sorted(seqs)


def test_p05_a3_drill_additive_and_ids_survive(monkeypatch):
    """drill(大纲稳定id)：子树深扫增量、原有条目与句柄全部存活可 act。"""
    root, shallow, deep, _ = _a3_deep_tree()
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    els = b.snapshot()
    shallow_eid = find_el(els, "浅层按钮").element_id
    outline = next(p for p in b.last_projection() if p["name"] == "折叠容器")
    out = b.drill(outline["id"])
    assert {e.text for e in out} == {"深层按钮"}
    deep_eid = out[0].element_id
    # drill 是加法：原视图与句柄未被重置
    assert shallow_eid in b._last_controls
    r1 = b.act(deep_eid, action="click", verify_timeout=0.2)
    assert r1["success"] is True and "invoke" in deep.log
    r2 = b.act(shallow_eid, action="click", verify_timeout=0.2)
    assert r2["success"] is True and "invoke" in shallow.log
    # 深层条目并入投影（原位置之外的增量尾部，seq 续编）
    assert any(p["name"] == "深层按钮" for p in b.last_projection())


def test_p05_a3_outline_merges_into_existing_entry(monkeypatch):
    """容器本身已在投影（白名单类型）→ 大纲字段原地合并，不产第二条目。"""
    opt = FakeControl("选项甲", ctype="MenuItemControl", rect=(10, 320, 60, 340))
    combo = _RuntimeIdControl("下拉框", ctype="ComboBoxControl",
                              rect=(5, 300, 200, 345), runtime_id=(2, 1),
                              children=(opt,))
    combo._patterns["expand"] = _FakeExpandPattern(combo)
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600),
                       children=(combo,))
    install_fake_uia(monkeypatch, root)
    b = UIABridge()
    # combo 在 d1（默认 depth 3 内）→ 无折叠。压 depth=1 让它落在 d==max_depth：
    els = b.snapshot(max_depth=1)
    entries = [p for p in b.last_projection() if p["name"] == "下拉框"]
    assert len(entries) == 1
    assert entries[0]["expandable"] is True and entries[0]["items"] == 1
    assert "expandcollapse" in entries[0]["patterns"]  # 原 pattern 字段保留
    assert not any(p["name"] == "选项甲" for p in b.last_projection())


def test_p05_a3_agent_scope_drill_returns_subtree_and_survival(monkeypatch):
    """agent scope=大纲 id → mode drill/additive，子树控件进投影且可 act，
    原窗口条目 id 不失效。"""
    root, shallow, deep, _ = _a3_deep_tree()
    install_fake_uia(monkeypatch, root)
    a = agent_mod.ExecutionAgent()
    obs = a._do_get_screen_info()
    outline = next(e for e in obs["elements"] if e.get("expandable")
                   and e["name"] == "折叠容器")
    obs2 = a._do_get_screen_info(scope=outline["id"])
    assert obs2["success"] and obs2["mode"] == "drill" and obs2["additive"] is True
    assert obs2["scope"] == outline["id"]
    deep_e = next(e for e in obs2["elements"] if e["name"] == "深层按钮")
    r = a.dispatch_tool("click", {"element_id": deep_e["id"], "name": "深层按钮"})
    assert r["ok"] is True and "invoke" in deep.log
    shallow_e = next(e for e in obs["elements"] if e["name"] == "浅层按钮")
    r2 = a.dispatch_tool("click", {"element_id": shallow_e["id"], "name": "浅层按钮"})
    assert r2["ok"] is True  # 其余 id 不失效
    # scope 未知 id → element_not_found 语义
    r3 = a._do_get_screen_info(scope="e000000000")
    assert r3["success"] is False and r3["error_code"] == "element_not_found"


def test_p05_a3_scope_on_temp_outline_id_errors(monkeypatch):
    """scope 指向 o{n} 大纲临时 id → scope_not_drillable + 先整窗观察 hint。"""
    root, *_ = _a3_deep_tree()
    install_fake_uia(monkeypatch, root)
    a = agent_mod.ExecutionAgent()
    obs = a._do_get_screen_info()
    o_id = next(e["id"] for e in obs["elements"] if e["id"].startswith("o"))
    r = a._do_get_screen_info(scope=o_id)
    assert r["success"] is False and r["error_code"] == "scope_not_drillable"
    assert "整窗观察" in r["hint"]
    d = a.dispatch_tool("get_screen_info", {"scope": o_id})
    assert d["ok"] is False and d["error_code"] == "scope_not_drillable"


def test_p05_a3_filter_lexical_priority_and_off():
    """词法命中（×8）压过可交互（×4）；filter '-'/缺省 step_text 两条路径。"""
    a = agent_mod.ExecutionAgent()
    proj = [
        {"id": f"e{i}", "type": "button", "name": f"条目{i}", "class": "",
         "enabled": True, "patterns": [], "bbox": [i, 0, 10, 10], "seq": i}
        for i in range(50)
    ]
    proj[3]["patterns"] = ["invoke"]  # 唯一可交互对照组
    proj[41]["name"] = "下载到磁盘按钮"  # 非交互但语义命中
    out = a._prioritize_projection(proj, query="下载")
    assert out[0]["id"] == "e41"  # 含"下载"条目优先于其他（含可交互）条目
    ids = [e["id"] for e in out]
    assert "e41" in ids and ids.index("e41") < ids.index("e3")
    out_off = a._prioritize_projection(proj, query="-")
    # 关闭语义层 → 纯旧打分：e3（唯一可交互）入选、e41 掉出截断集，
    # 输出按快照序重排（旧行为头名是 DFS 首位，不是 e3）。
    ids_off = [e["id"] for e in out_off]
    assert out_off[0]["id"] == "e0"
    assert "e3" in ids_off and "e41" not in ids_off
    a._step_text = "点击下载并保存"  # 缺省 query=本步 instruction
    out_def = a._prioritize_projection(proj)
    assert out_def[0]["id"] == "e41"


def test_p05_a3_agent_filter_param_and_off_via_observation(monkeypatch):
    """整窗观察走 filter 参数覆盖缺省 query（经真实桥的截断路径太贵，
    用 41+ 条目浅树验证参数接线不改语义即可）。"""
    kids = [FakeControl(f"k{i}", ctype="ButtonControl",
                        rect=(i, 50 + i, i + 30, 80 + i)) for i in range(45)]
    for k in kids:
        k._patterns["invoke"] = _FakeInvokePattern(k)
    kids[44].Name = "下载入口"
    root = FakeControl("窗口", ctype="WindowControl", rect=(0, 0, 800, 600),
                       children=tuple(kids))
    install_fake_uia(monkeypatch, root)
    a = agent_mod.ExecutionAgent()
    a._step_text = "下载"
    obs = a._do_get_screen_info()
    assert obs["success"] and len(obs["elements"]) == a._SCREEN_PROJECTION_LIMIT
    assert obs["elements"][0]["name"] == "下载入口"  # 语义层生效
    obs2 = a._do_get_screen_info(filter="-")
    assert obs2["elements"][0]["name"] == "k0"  # 关闭后回 DFS 原序头名
    assert obs2.get("truncated")  # 截断事实仍可见


def test_p05_a3_schema_prompt_config_wiring():
    gsi = next(t for t in agent_mod.ExecutionAgent().tools
               if t["function"]["name"] == "get_screen_info")
    assert set(gsi["function"]["parameters"]["properties"]) == {
        "scope", "depth", "filter"
    }
    prompt = agent_mod.EXECUTION_SYSTEM_PROMPT
    assert "下钻" in prompt and "expandable" in prompt  # 策略行入 prompt
    from server.config import settings
    assert settings.SCREEN_SEMANTIC_FILTER is False  # embedding 层默认关
