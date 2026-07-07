"""WPS 启发 collector — 顶栏菜单与工具栏。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from server.services.assist.types import AssistContext, CandidateElement

_PROFILE_PATH = Path(__file__).resolve().parent.parent / "profiles" / "wps_1080p.json"

_WPS_KEYWORDS = ("wps", "金山", "et.exe", "wps.exe", "wpp.exe")


def _load_profile() -> Dict[str, Any]:
    try:
        if _PROFILE_PATH.is_file():
            return json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _rect_from_relative(
    fg_rect: List[int],
    rel: Dict[str, float],
) -> List[int]:
    left, top, right, bottom = [int(v) for v in fg_rect[:4]]
    w = max(1, right - left)
    h = max(1, bottom - top)
    x1 = left + int(w * rel.get("x1", 0))
    y1 = top + int(h * rel.get("y1", 0))
    x2 = left + int(w * rel.get("x2", 1))
    y2 = top + int(h * rel.get("y2", 1))
    return [x1, y1, x2, y2]


class WPSHeuristicCollector:
    name = "wps"

    def supports(self, ctx: AssistContext) -> bool:
        if ctx.scene_hint == "wps":
            return True
        title = (ctx.foreground.get("window_title") or "").lower()
        proc = (ctx.foreground.get("process_name") or "").lower()
        return any(k in title or k in proc for k in _WPS_KEYWORDS)

    def collect(self, ctx: AssistContext) -> List[CandidateElement]:
        fg_rect = ctx.foreground.get("rect")
        if not fg_rect or len(fg_rect) < 4:
            return []
        profile = _load_profile()
        regions = profile.get("toolbar_regions") or []
        out: List[CandidateElement] = []
        for region in regions:
            if not isinstance(region, dict):
                continue
            name = (region.get("name") or "").strip()
            rel = region.get("relative_bbox")
            if not name or not isinstance(rel, dict):
                continue
            out.append(
                CandidateElement(
                    name=name,
                    bbox=_rect_from_relative(fg_rect, rel),
                    confidence=float(region.get("confidence", 0.6)),
                    source="wps",
                    element_type=region.get("element_type", "button"),
                    meta={"profile": "wps_1080p"},
                )
            )
        menu_y = profile.get("menu_bar_y_range") or [0.0, 0.06]
        out.append(
            CandidateElement(
                name="开始",
                bbox=_rect_from_relative(
                    fg_rect,
                    {"x1": 0.0, "y1": menu_y[0], "x2": 0.08, "y2": menu_y[1]},
                ),
                confidence=0.58,
                source="wps",
                element_type="menu",
            )
        )
        out.append(
            CandidateElement(
                name="合并单元格",
                bbox=_rect_from_relative(
                    fg_rect,
                    {"x1": 0.35, "y1": menu_y[1], "x2": 0.48, "y2": menu_y[1] + 0.06},
                ),
                confidence=0.55,
                source="wps",
                element_type="button",
                meta={"heuristic": True},
            )
        )
        return out
