"""Collector 注册表 — fail-open。"""
from __future__ import annotations

from typing import List, Protocol

from server.services.assist.config import (
    ASSIST_BROWSER_ENABLED,
    ASSIST_DESKTOP_SHORTCUTS,
    ASSIST_ENABLED,
    ASSIST_UIA_ENABLED,
    ASSIST_WPS_ENABLED,
)
from server.services.assist.types import AssistContext, CandidateElement


class AssistCollector(Protocol):
    name: str

    def supports(self, ctx: AssistContext) -> bool: ...

    def collect(self, ctx: AssistContext) -> List[CandidateElement]: ...


def _all_collectors() -> List[AssistCollector]:
    from server.services.assist.collectors.browser import BrowserHeuristicCollector
    from server.services.assist.collectors.desktop import DesktopShortcutCollector
    from server.services.assist.collectors.uia import UIACollector
    from server.services.assist.collectors.wps import WPSHeuristicCollector

    collectors: List[AssistCollector] = []
    if ASSIST_DESKTOP_SHORTCUTS:
        collectors.append(DesktopShortcutCollector())
    if ASSIST_UIA_ENABLED:
        collectors.append(UIACollector())
    if ASSIST_BROWSER_ENABLED:
        collectors.append(BrowserHeuristicCollector())
    if ASSIST_WPS_ENABLED:
        collectors.append(WPSHeuristicCollector())
    return collectors


def run_collectors(ctx: AssistContext) -> List[CandidateElement]:
    if not ASSIST_ENABLED:
        return []
    out: List[CandidateElement] = []
    seen: set = set()
    for collector in _all_collectors():
        try:
            if not collector.supports(ctx):
                continue
            for cand in collector.collect(ctx):
                key = (cand.name, tuple(cand.bbox), cand.source)
                if key in seen:
                    continue
                seen.add(key)
                out.append(cand)
        except Exception:
            continue
    return out
