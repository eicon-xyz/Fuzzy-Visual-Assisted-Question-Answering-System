"""共享文本匹配 — L3 auto_bind 与 Assist TextMatch 复用。"""
from __future__ import annotations

from typing import List, Optional, Tuple

from server.models.schemas import UIElement


def text_match_element(
    description: str,
    action: str,
    elements: List[UIElement],
) -> Optional[Tuple[UIElement, float]]:
    combined = (description + " " + action).lower()
    keywords = [kw for kw in combined.split() if len(kw) >= 2]
    best: Optional[Tuple[UIElement, float]] = None
    for e in elements:
        text = (e.text or "").strip()
        if not text:
            continue
        text_lower = text.lower()
        if text_lower in combined:
            score = min(1.0, len(text_lower) / max(len(combined), 1) * 4)
        else:
            hits = sum(1 for kw in keywords if kw in text_lower)
            if not hits:
                continue
            score = hits / max(len(keywords), 1)
        if best is None or score > best[1]:
            best = (e, score)
    return best
