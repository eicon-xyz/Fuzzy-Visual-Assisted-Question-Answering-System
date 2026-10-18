"""Phase 1 单测：许可令牌、策略派生、拒绝形状。

全部不碰真实桌面：hid 的 `_move_raw` / `_click_raw` / `_hotkey_raw` 被替换成
记录器，因此这些测试在任何机器上都能跑（Windows/CI/无显示器）。
"""

from __future__ import annotations

import pytest

from server.services.executor import hid
from server.services.executor.permit import (
    BROKER,
    ForegroundAction,
    ForegroundPermit,
    PermitBroker,
    TaskPolicy,
    derive_policy,
)


def _spy_hid(monkeypatch) -> list:
    """装上 hid 设备层探针：任何真实键鼠调用都会落进返回的列表。"""
    calls: list[tuple] = []
    monkeypatch.setattr(hid, "_move_raw", lambda x, y, duration=0.2: calls.append(("move", x, y)))
    monkeypatch.setattr(hid, "_click_raw", lambda button="left", clicks=1: calls.append(("click", button, clicks)))
    monkeypatch.setattr(hid, "_hotkey_raw", lambda *k: calls.append(("hotkey", k)))
    return calls


def _permit(actions, task_id="t", ttl_s=60.0) -> ForegroundPermit:
    broker = PermitBroker()
    policy = TaskPolicy(task_id=task_id, actions=frozenset(actions))
    return broker.resolve(policy, consent=True, ttl_s=ttl_s)


# ── 令牌 ────────────────────────────────────────────────────────────────────


def test_permit_cannot_be_forged():
    """令牌只能由 broker 铸造；直接构造必须 TypeError。"""
    with pytest.raises(TypeError):
        ForegroundPermit(object(), "t", {ForegroundAction.POINTER})


def test_permit_expires():
    p = _permit({ForegroundAction.POINTER}, ttl_s=1.0)
    assert p.live is True
    p.expires_at = 0.0  # 模拟过期
    assert p.live is False
    assert p.allows(ForegroundAction.POINTER) is False


def test_permit_scope_is_per_action():
    p = _permit({ForegroundAction.POINTER})
    assert p.allows(ForegroundAction.POINTER)
    assert not p.allows(ForegroundAction.KEYBOARD)


# ── 拒绝语义（fail-closed）────────────────────────────────────────────────


def test_click_without_permit_is_refused(monkeypatch):
    calls = _spy_hid(monkeypatch)
    r = hid.click(None, (100, 100))
    assert r.ok is False
    assert r.error_code == "permit_required"
    assert r.to_dict()["required_actions"] == ["pointer"]
    assert calls == [], "拒绝时绝不能碰真实输入"


def test_click_without_pointer_scope_is_refused(monkeypatch):
    calls = _spy_hid(monkeypatch)
    p = _permit({ForegroundAction.KEYBOARD})
    r = hid.click(p, (100, 100))
    assert r.error_code == "permit_required"
    assert r.to_dict()["granted_actions"] == ["keyboard"]
    assert calls == []


def test_click_with_permit_executes_once(monkeypatch):
    calls = _spy_hid(monkeypatch)
    p = _permit({ForegroundAction.POINTER})
    r = hid.click(p, (100, 100))
    assert r.ok is True
    assert [c[0] for c in calls] == ["move", "click"]


def test_revoked_permit_is_refused(monkeypatch):
    calls = _spy_hid(monkeypatch)
    broker = PermitBroker()
    policy = TaskPolicy(task_id="t9", actions=frozenset({ForegroundAction.POINTER}))
    p = broker.resolve(policy, consent=True)
    broker.revoke("t9")
    r = hid.click(p, (1, 1))
    assert r.error_code == "permit_revoked"


def test_paste_needs_two_scopes(monkeypatch):
    calls = _spy_hid(monkeypatch)
    p = _permit({ForegroundAction.CLIPBOARD})
    r = hid.paste(p, "hi")
    assert r.error_code == "permit_required"
    assert set(r.to_dict()["required_actions"]) == {"clipboard", "keyboard"}
    assert calls == []


def test_hotkey_scope(monkeypatch):
    calls = _spy_hid(monkeypatch)
    assert hid.hotkey(None, "ctrl", "s").error_code == "permit_required"
    p = _permit({ForegroundAction.KEYBOARD})
    assert hid.hotkey(p, "ctrl", "s").ok is True
    assert calls == [("hotkey", ("ctrl", "s"))]


def test_precheck_does_not_execute(monkeypatch):
    calls = _spy_hid(monkeypatch)
    p = _permit({ForegroundAction.ACTIVATE})
    denied = hid.precheck(p, (ForegroundAction.ACTIVATE, ForegroundAction.CLIPBOARD), "x")
    assert denied is not None and set(denied["required_actions"]) == {
        "activate",
        "clipboard",
    }
    assert calls == []


# ── 策略派生（确定性，不让模型填）─────────────────────────────────────────


def test_policy_without_hid_verbs_is_not_exclusive():
    p = derive_policy("t", "查看当前列表内容", [{"instruction": "读取标题文本"}])
    assert p.exclusive is False
    assert p.actions == frozenset()


def test_policy_detects_pointer_and_keyboard():
    p = derive_policy(
        "t",
        "打开记事本并输入你好",
        [{"instruction": "双击图标"}, {"instruction": "在输入框输入文本"}],
    )
    assert p.exclusive is True
    assert ForegroundAction.POINTER in p.actions
    assert ForegroundAction.KEYBOARD in p.actions
    # reasons 必须能解释命中，否则不可审计
    assert any("pointer" in r for r in p.reasons)


def test_policy_is_deterministic():
    a = derive_policy("t", "打开计算器", [{"instruction": "点击按钮"}])
    b = derive_policy("t", "打开计算器", [{"instruction": "点击按钮"}])
    assert a.actions == b.actions
    assert a.reasons == b.reasons


def test_policy_no_consent_denies():
    broker = PermitBroker()
    policy = TaskPolicy(task_id="t", actions=frozenset({ForegroundAction.POINTER}))
    assert broker.resolve(policy, consent=False) is None
    assert broker.resolve(policy, consent=True) is not None


def test_non_exclusive_never_prompts():
    broker = PermitBroker()
    policy = TaskPolicy(task_id="t", actions=frozenset())
    assert broker.resolve(policy, consent=True) is None


def test_global_broker_grants_and_revokes():
    policy = derive_policy("glob", "打开记事本", [])
    permit = BROKER.resolve(policy, consent=True)
    try:
        assert permit is not None and permit.live
    finally:
        BROKER.revoke("glob")
    assert permit.live is False


# ── 坐标钳制（修掉旧 clicker 的 1920×1080 硬编码）─────────────────────────


def test_clamp_uses_real_screen_size(monkeypatch):
    """2K 屏上 x=2000 不能被压到 1915（旧的 1920×1080 默认值会这么干）。"""
    monkeypatch.setattr(hid, "screen_size", lambda: (2560, 1440))
    x, y = hid._clamp((2000, 1200))
    assert (x, y) == (2000, 1200)


def test_clamp_keeps_point_inside_screen(monkeypatch):
    monkeypatch.setattr(hid, "screen_size", lambda: (1920, 1080))
    assert hid._clamp((10_000, 10_000)) == (1915, 1075)
    assert hid._clamp((-50, -50)) == (5, 5)
