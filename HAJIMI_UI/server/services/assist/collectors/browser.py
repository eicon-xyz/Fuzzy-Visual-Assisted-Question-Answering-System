"""浏览器启发 collector — Chrome/Edge/Firefox 顶栏控件。"""
from __future__ import annotations

from typing import List

from server.services.assist.types import AssistContext, CandidateElement

_BROWSER_PROCS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}


class BrowserHeuristicCollector:
    name = "browser"

    def supports(self, ctx: AssistContext) -> bool:
        if ctx.scene_hint == "browser":
            return True
        proc = (ctx.foreground.get("process_name") or "").lower()
        return proc in _BROWSER_PROCS

    def collect(self, ctx: AssistContext) -> List[CandidateElement]:
        fg_rect = ctx.foreground.get("rect")
        if not fg_rect or len(fg_rect) < 4:
            return []
        left, top, right, bottom = [int(v) for v in fg_rect[:4]]
        width = max(1, right - left)
        height = max(1, bottom - top)
        toolbar_h = min(120, int(height * 0.12))
        out: List[CandidateElement] = []
        out.append(
            CandidateElement(
                name="地址栏",
                bbox=[left + int(width * 0.08), top + int(toolbar_h * 0.2), left + int(width * 0.75), top + toolbar_h],
                confidence=0.55,
                source="browser",
                element_type="textfield",
                meta={"heuristic": True},
            )
        )
        out.append(
            CandidateElement(
                name="刷新",
                bbox=[left + int(width * 0.02), top + int(toolbar_h * 0.15), left + int(width * 0.06), top + int(toolbar_h * 0.85)],
                confidence=0.5,
                source="browser",
                element_type="button",
                meta={"heuristic": True},
            )
        )
        return out
