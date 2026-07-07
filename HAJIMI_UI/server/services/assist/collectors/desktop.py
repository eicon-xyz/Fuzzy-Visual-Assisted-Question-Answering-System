"""桌面快捷方式 collector — 使用 B 端 local_candidates + 名称匹配。"""
from __future__ import annotations

import re
from typing import List

from server.services.assist.types import AssistContext, CandidateElement


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", (name or "").lower())


class DesktopShortcutCollector:
    name = "desktop"

    def supports(self, ctx: AssistContext) -> bool:
        scene = ctx.scene_hint
        fg = ctx.foreground
        proc = (fg.get("process_name") or "").lower()
        return scene == "desktop" or "explorer" in proc

    def collect(self, ctx: AssistContext) -> List[CandidateElement]:
        local = ctx.bundle.get("local_candidates") or []
        out: List[CandidateElement] = []
        for item in local:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            if not name:
                continue
            bbox = item.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            out.append(
                CandidateElement(
                    name=name,
                    bbox=[int(b) for b in bbox[:4]],
                    confidence=0.85,
                    source="desktop_shortcut",
                    element_type="shortcut",
                )
            )
        return out
