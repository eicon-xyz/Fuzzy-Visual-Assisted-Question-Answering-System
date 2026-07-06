"""
Route selection: L2 / L3 (OmniParser) / L3_DEFERRED / L4 (Vision) / BROWSER.
"""
from __future__ import annotations

from typing import Optional

from server.config import settings
from server.services.planning.complexity_router import l2_steps_skip_parse_with_image
from server.services.plugins.browser_router import is_browser_task, browser_route_available

VALID_ROUTES = ("L2", "L3", "L3_DEFERRED", "L4", "BROWSER")


def select_route(
    query: str,
    *,
    has_image: bool,
    l2_steps: Optional[list] = None,
) -> str:
    """
    Pick processing route based on config and query.
    """
    if l2_steps and (not has_image or l2_steps_skip_parse_with_image(l2_steps)):
        return "L2"

    routing_mode = (getattr(settings, "ROUTING_MODE", None) or "auto").lower()
    if routing_mode not in ("auto", "fast", "balanced", "precision"):
        routing_mode = "auto"

    # L2 模板命中但带截图且非 keyboard_only：沿用原 L3 OmniParser 绑定路径
    if l2_steps and has_image and not l2_steps_skip_parse_with_image(l2_steps):
        return "L3"

    if getattr(settings, "BROWSER_PLUGIN_ENABLED", True) and is_browser_task(query):
        if browser_route_available():
            return "BROWSER"

    if not has_image:
        return "L3"

    if routing_mode == "precision":
        return "L3"
    if routing_mode == "balanced":
        return "L3_DEFERRED"
    if routing_mode == "fast":
        return "L4"
    # auto: prefer L4 for speed (OpenGuider-style)
    return "L4"


def route_skips_omniparser(route: str) -> bool:
    return route in ("L2", "L4", "L3_DEFERRED", "BROWSER")


def route_uses_per_step_locate(route: str) -> bool:
    return route in ("L4", "L3_DEFERRED")
