"""路由选择回归测试：无 :9800 纯视觉模式下模板查询不再强制走 L3/OmniParser。"""
from __future__ import annotations

from server.config import settings
from server.services.planning.route_selector import select_route

_L2_TEMPLATE_STEPS = [{"_l2_keyboard_only": False, "action": "open_app"}]
_L2_KEYBOARD_STEPS = [{"_l2_keyboard_only": True, "action": "press_key"}]


def test_template_with_image_goes_l4_when_omni_disabled(monkeypatch):
    monkeypatch.setattr(settings, "OMNIPARSER_ENABLED", False)
    monkeypatch.setattr(settings, "ROUTING_MODE", "fast")
    route = select_route("打开计算器", has_image=True, l2_steps=_L2_TEMPLATE_STEPS)
    assert route == "L4"


def test_template_with_image_still_l3_when_omni_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OMNIPARSER_ENABLED", True)
    monkeypatch.setattr(settings, "ROUTING_MODE", "fast")
    route = select_route("打开计算器", has_image=True, l2_steps=_L2_TEMPLATE_STEPS)
    assert route == "L3"


def test_keyboard_template_stays_l2(monkeypatch):
    monkeypatch.setattr(settings, "OMNIPARSER_ENABLED", False)
    monkeypatch.setattr(settings, "ROUTING_MODE", "fast")
    route = select_route("最小化窗口", has_image=True, l2_steps=_L2_KEYBOARD_STEPS)
    assert route == "L2"
