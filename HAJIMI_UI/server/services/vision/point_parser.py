"""
Parse Vision-LLM [POINT:x,y:label] tags and map normalized coords to screen pixels.
Inspired by OpenGuider src/ai/index.js + pointer-tool.js.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from server.models.schemas import Annotation, UIElement

_POINT_RE = re.compile(
    r"\[POINT:(?:none|([\d.]+)\s*,\s*([\d.]+)(?::([^\]:]+))?)\]",
    re.IGNORECASE,
)
_FALLBACK_PAREN_RE = re.compile(r"\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\)")


def parse_point_tag(text: str) -> Tuple[str, Optional[dict], Optional[str]]:
    """
    Extract first valid [POINT:x,y:label] from LLM output.

    Returns:
        (clean_text, coordinate_dict_or_none, label_or_none)
        coordinate uses 0-1000 normalized scale when from POINT tag.
    """
    if not text:
        return "", None, None

    first_coord: Optional[dict] = None
    first_label: Optional[str] = None

    def _replacer(match: re.Match) -> str:
        nonlocal first_coord, first_label
        x, y, label = match.group(1), match.group(2), match.group(3)
        if x and y and first_coord is None:
            first_coord = {"x": float(x), "y": float(y)}
            first_label = (label or "element").strip() or "element"
        return ""

    clean = _POINT_RE.sub(_replacer, text).strip()
    if first_coord:
        return clean, first_coord, first_label

    fb = _FALLBACK_PAREN_RE.search(text)
    if fb:
        return (
            text.replace(fb.group(0), "").strip(),
            {"x": float(fb.group(1)), "y": float(fb.group(2))},
            "element",
        )
    return clean or text.strip(), None, None


def normalized_to_pixel(
    x: float,
    y: float,
    width: int,
    height: int,
) -> Tuple[int, int]:
    """Map 0-1000 (or 0-1) normalized coords to pixel center."""
    if 0 < x <= 1 and 0 < y <= 1:
        px = int(round(x * width))
        py = int(round(y * height))
    elif 0 < x <= 1000 and 0 < y <= 1000:
        px = int(round((x / 1000.0) * width))
        py = int(round((y / 1000.0) * height))
    else:
        px = int(round(x))
        py = int(round(y))
    px = max(0, min(width - 1, px))
    py = max(0, min(height - 1, py))
    return px, py


def normalized_point_to_bbox(
    x: float,
    y: float,
    width: int,
    height: int,
    *,
    box_half: int = 24,
) -> List[int]:
    """Build a small highlight bbox around the normalized point."""
    cx, cy = normalized_to_pixel(x, y, width, height)
    x1 = max(0, cx - box_half)
    y1 = max(0, cy - box_half)
    x2 = min(width, cx + box_half)
    y2 = min(height, cy + box_half)
    return [x1, y1, x2, y2]


def build_annotation_from_point(
    x: float,
    y: float,
    width: int,
    height: int,
    *,
    label: str = "点击此处",
    annotation_type: str = "arrow_highlight",
) -> Annotation:
    cx, cy = normalized_to_pixel(x, y, width, height)
    bbox = normalized_point_to_bbox(x, y, width, height)
    x1, y1, _, _ = bbox
    return Annotation(
        type=annotation_type,
        arrow_from=[max(0, cx - 120), max(0, cy - 80)],
        arrow_to=[cx, cy],
        highlight_bbox=bbox,
        label_position=[x1, max(0, y1 - 36)],
        label_text=label,
    )


def build_synthetic_element(
    x: float,
    y: float,
    width: int,
    height: int,
    *,
    element_id: str = "~vision",
    label: str = "",
) -> UIElement:
    bbox = normalized_point_to_bbox(x, y, width, height)
    cx, cy = normalized_to_pixel(x, y, width, height)
    return UIElement(
        element_id=element_id,
        bbox=bbox,
        element_type="other",
        text=label or "vision_target",
        confidence=0.75,
        center=[cx, cy],
    )
