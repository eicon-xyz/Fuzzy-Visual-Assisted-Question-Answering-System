"""步骤推进进度文案 — 按任务实际 route 选择，与 L4 实现解耦。"""
from __future__ import annotations

from typing import Optional

_VISION_LOCATE_ROUTES = frozenset({"L4", "L3_DEFERRED"})
_OMNIPARSER_REPLAN_ROUTE = "L3"


def advance_locate_message(
    route: Optional[str],
    action: str,
    *,
    has_screenshot: bool = True,
) -> str:
    """按 A 端返回的 route 与 action 返回 advance 阶段用户可见文案。"""
    if action != "advance":
        return "步骤推进中…"
    if not has_screenshot:
        return "步骤推进中…"

    name = (route or "").upper()
    if name in _VISION_LOCATE_ROUTES:
        return "Vision 定位中…"
    if name == _OMNIPARSER_REPLAN_ROUTE:
        return "OmniParser 重检测中…"
    return "步骤推进中…"
