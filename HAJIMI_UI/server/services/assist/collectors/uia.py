"""浅层 UIA 控件树 collector。"""
from __future__ import annotations

import platform
from typing import List, Optional

from server.services.assist.types import AssistContext, CandidateElement

_MAX_DEPTH = 3
_MAX_NODES = 50


def _control_bbox(control) -> Optional[List[int]]:
    try:
        rect = control.BoundingRectangle
        if not rect:
            return None
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        if right <= left or bottom <= top:
            return None
        return [int(left), int(top), int(right), int(bottom)]
    except Exception:
        return None


def _walk(control, depth: int, out: List[CandidateElement], budget: List[int]) -> None:
    if depth > _MAX_DEPTH or budget[0] <= 0:
        return
    budget[0] -= 1
    try:
        name = (control.Name or "").strip()
        ctrl_type = getattr(control, "ControlTypeName", "") or ""
        bbox = _control_bbox(control)
        if name and bbox:
            element_type = "button" if "Button" in ctrl_type else "text"
            out.append(
                CandidateElement(
                    name=name,
                    bbox=bbox,
                    confidence=0.75,
                    source="uia",
                    element_type=element_type,
                )
            )
        children = control.GetChildren()
        for child in children:
            if budget[0] <= 0:
                break
            _walk(child, depth + 1, out, budget)
    except Exception:
        return


class UIACollector:
    name = "uia"

    def supports(self, ctx: AssistContext) -> bool:
        return platform.system() == "Windows"

    def collect(self, ctx: AssistContext) -> List[CandidateElement]:
        try:
            import uiautomation as auto  # type: ignore
        except ImportError:
            return []
        out: List[CandidateElement] = []
        try:
            fg = auto.GetForegroundControl()
            if not fg:
                return []
            _walk(fg, 0, out, [_MAX_NODES])
        except Exception:
            return []
        return out
