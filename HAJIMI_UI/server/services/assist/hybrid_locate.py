"""Hybrid 融合定位 — 结构化命中则跳过 Vision。"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from server.models.schemas import UIElement
from server.services.assist.config import ASSIST_HYBRID_MIN_CONFIDENCE, ASSIST_ENABLED
from server.services.assist.types import AssistContext, CandidateElement, HybridLocateResult
from server.services.planning.annotation import build_annotation

_ALIASES = {
    "chrome": ["google chrome", "谷歌浏览器", "chrome浏览器"],
    "edge": ["microsoft edge", "msedge"],
    "firefox": ["火狐", "mozilla firefox"],
    "回收站": ["recycle bin"],
    "合并单元格": ["merge cells", "合并"],
    "地址栏": ["address bar", "url bar", "网址栏"],
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _expand_targets(step: dict, user_query: str) -> List[str]:
    parts = [
        step.get("target") or "",
        step.get("description") or "",
        step.get("action") or "",
        user_query or "",
    ]
    targets: List[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in targets:
            targets.append(p)
    expanded = list(targets)
    for t in targets:
        key = _normalize(t)
        for alias_key, alias_list in _ALIASES.items():
            if alias_key in key or key in alias_key:
                expanded.append(alias_key)
                expanded.extend(alias_list)
    return expanded


def _string_score(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return min(1.0, max(len(na), len(nb)) / max(len(nb), len(na), 1))
    return SequenceMatcher(None, na, nb).ratio()


def _type_weight(element_type: str) -> float:
    weights = {
        "button": 1.0,
        "menu": 0.95,
        "textfield": 0.9,
        "shortcut": 0.88,
        "text": 0.8,
    }
    return weights.get(element_type, 0.75)


def _in_foreground(bbox: List[int], fg_rect: Optional[List[int]]) -> bool:
    if not fg_rect or len(fg_rect) < 4 or len(bbox) < 4:
        return True
    cx = (bbox[0] + bbox[2]) // 2
    cy = (bbox[1] + bbox[3]) // 2
    left, top, right, bottom = fg_rect[:4]
    return left <= cx <= right and top <= cy <= bottom


def score_candidate(
    cand: CandidateElement,
    targets: List[str],
    fg_rect: Optional[List[int]],
) -> float:
    best = 0.0
    for t in targets:
        best = max(best, _string_score(t, cand.name))
    score = best * 0.7 + cand.confidence * 0.2 + _type_weight(cand.element_type) * 0.1
    if _in_foreground(cand.bbox, fg_rect):
        score += 0.05
    return min(1.0, score)


def _map_element_type(element_type: str) -> str:
    mapping = {
        "button": "button",
        "menu": "menu",
        "textfield": "input",
        "shortcut": "icon",
        "text": "text",
    }
    return mapping.get(element_type, "other")


def _candidate_to_element(cand: CandidateElement) -> UIElement:
    x1, y1, x2, y2 = cand.bbox[:4]
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    return UIElement(
        element_id=f"assist_{cand.source}_{cand.name[:24]}",
        text=cand.name,
        bbox=cand.bbox,
        center=[cx, cy],
        confidence=cand.confidence,
        element_type=_map_element_type(cand.element_type),
    )


def try_hybrid_locate(
    step: dict,
    *,
    image_b64: str,
    user_query: str,
    ctx: AssistContext,
) -> HybridLocateResult:
    if not ASSIST_ENABLED:
        return HybridLocateResult(hit=False, meta={"skipped": "assist_disabled"})
    if not ctx.candidates:
        return HybridLocateResult(hit=False, meta={"skipped": "no_candidates"})

    targets = _expand_targets(step, user_query)
    fg_rect = ctx.foreground.get("rect")
    best: Optional[Tuple[CandidateElement, float]] = None
    for cand in ctx.candidates:
        if not cand.bbox or len(cand.bbox) < 4:
            continue
        score = score_candidate(cand, targets, fg_rect)
        if best is None or score > best[1]:
            best = (cand, score)

    if not best or best[1] < ASSIST_HYBRID_MIN_CONFIDENCE:
        return HybridLocateResult(
            hit=False,
            meta={"best_score": best[1] if best else 0.0, "threshold": ASSIST_HYBRID_MIN_CONFIDENCE},
        )

    cand, score = best
    element = _candidate_to_element(cand)
    label = step.get("target") or step.get("description") or cand.name
    annotation = build_annotation(
        element,
        annotation_type="arrow_highlight",
        label_text=label[:40],
    )
    ref = None
    if ctx.capture_size and len(ctx.capture_size) >= 2:
        ref = [int(ctx.capture_size[0]), int(ctx.capture_size[1])]
    return HybridLocateResult(
        hit=True,
        annotation=annotation,
        reference_resolution=ref,
        source=cand.source,
        meta={"score": score, "candidate": cand.name, "assist_source": cand.source},
    )
