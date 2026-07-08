"""
Local OmniParser V2 HTTP client.

The OmniParser API server is deployed separately (D:\\ominprester) and exposes
POST /parse, which returns structured UI elements for a base64-encoded image.
This module converts those elements into the HAJIMI UIElement schema.
"""

import base64
import io
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

import httpx
from PIL import Image

from server.config import settings
from server.models.schemas import UIElement

_OMNIPARSER_URL = settings.OMNIPARSER_URL.rstrip("/")
_OMNIPARSER_TIMEOUT = settings.OMNIPARSER_TIMEOUT
_OMNIPARSER_RETRY = getattr(settings, "OMNIPARSER_RETRY", 1)
_OMNIPARSER_RETRY_DELAY = getattr(settings, "OMNIPARSER_RETRY_DELAY", 3.0)

# Regex to strip data URI prefix, e.g. "data:image/png;base64,"
_DATA_URI_RE = re.compile(r"^data:image/\w+;base64,")


def _compress_som_image(image_b64: str, max_side: int = 1024, quality: int = 85) -> str:
    """Compress SoM image → JPEG ≤max_side px. Falls back to original on error."""
    try:
        raw = image_b64
        if "," in raw and raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        img_bytes = base64.b64decode(raw)
        img = Image.open(io.BytesIO(img_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > max_side:
            ratio = max_side / max(w, h)
            new_size = (int(w * ratio), int(h * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        compressed = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{compressed}"
    except Exception as e:
        print(f"[compress] fallback to original: {e}")
        return image_b64


def _clean_base64(image_base64: Optional[str]) -> Optional[str]:
    if not image_base64:
        return None
    cleaned = _DATA_URI_RE.sub("", image_base64)
    # Remove any whitespace/newlines that may have been inserted by transport
    return cleaned.strip().replace("\n", "").replace("\r", "")


def _decode_image_resolution(payload_base64: str) -> Optional[List[int]]:
    """Try to decode image dimensions from base64 using PIL as fallback."""
    try:
        from PIL import Image

        raw = base64.b64decode(payload_base64)
        with Image.open(io.BytesIO(raw)) as img:
            return [img.width, img.height]
    except Exception:
        return None


@dataclass
class ParseResult:
    """Full result from OmniParser parse call."""

    elements: List[UIElement] = field(default_factory=list)
    annotated_image: Optional[str] = None
    reference_resolution: Optional[List[int]] = None
    detection_meta: Optional[dict] = None


def _compute_spatial_relations(elements: List[UIElement]) -> None:
    """Compute left/right/top/bottom neighbor relations for all elements.

    Mutates elements in-place, populating their *_elem_ids fields.

    Same row: y-axis IoU >= 0.3
    Top/bottom: x-axis overlap >= 0.1 (share horizontal space — elements in the same column)
    """
    n = len(elements)
    if n == 0:
        return

    # Reset all relation fields first
    for el in elements:
        el.left_elem_ids = []
        el.right_elem_ids = []
        el.top_elem_ids = []
        el.bottom_elem_ids = []

    for i in range(n):
        a = elements[i]
        ay1, ay2 = a.bbox[1], a.bbox[3]
        ax1, ax2 = a.bbox[0], a.bbox[2]
        ah = ay2 - ay1
        ax2 - ax1
        if ah <= 0:
            continue

        left_candidates = []
        right_candidates = []
        top_candidates = []
        bottom_candidates = []

        for j in range(n):
            if i == j:
                continue
            b = elements[j]
            by1, by2 = b.bbox[1], b.bbox[3]
            bx1, bx2 = b.bbox[0], b.bbox[2]
            bh = by2 - by1
            bx2 - bx1
            if bh <= 0:
                continue

            # y-axis intersection over union (for same-row detection)
            y_overlap = max(0, min(ay2, by2) - max(ay1, by1))
            y_union = max(ay2, by2) - min(ay1, by1)
            y_iou = y_overlap / y_union if y_union > 0 else 0

            # Same row for left/right: y-axis IoU >= 0.3
            if y_iou >= 0.3:
                if b.bbox[2] <= a.bbox[0]:  # b is to the left of a
                    left_candidates.append((j, a.bbox[0] - b.bbox[2]))
                elif b.bbox[0] >= a.bbox[2]:  # b is to the right of a
                    right_candidates.append((j, b.bbox[0] - a.bbox[2]))

            # Top/bottom: share horizontal space (x-overlap) AND one is above/below
            # Use x-axis overlap ratio >= 0.1 (elements in same column)
            x_overlap = max(0, min(ax2, bx2) - max(ax1, bx1))
            x_union = max(ax2, bx2) - min(ax1, bx1)
            x_iou = x_overlap / x_union if x_union > 0 else 0

            if x_iou >= 0.1:
                if by2 <= ay1:  # b is above a
                    top_candidates.append((j, ay1 - by2))
                elif by1 >= ay2:  # b is below a
                    bottom_candidates.append((j, by1 - ay2))

        # Sort by distance (ascending) and cap
        left_candidates.sort(key=lambda x: x[1])
        right_candidates.sort(key=lambda x: x[1])
        top_candidates.sort(key=lambda x: x[1])
        bottom_candidates.sort(key=lambda x: x[1])

        a.left_elem_ids = [elements[k].element_id for k, _ in left_candidates[:5]]
        a.right_elem_ids = [elements[k].element_id for k, _ in right_candidates[:5]]
        a.top_elem_ids = [elements[k].element_id for k, _ in top_candidates[:3]]
        a.bottom_elem_ids = [elements[k].element_id for k, _ in bottom_candidates[:3]]


def _filter_elements_for_llm(elements: List[UIElement]) -> List[dict]:
    """Return LLM-visible element data — no coordinates, no scores, no types.

    Each element dict contains only:
      - id: str (mapped from element_id)
      - content: str (mapped from text, empty string if None)
      - left_ids: List[str] (mapped from left_elem_ids)
      - right_ids: List[str] (mapped from right_elem_ids)
      - top_ids: List[str] (mapped from top_elem_ids)
      - bottom_ids: List[str] (mapped from bottom_elem_ids)
    """
    result = []
    for el in elements:
        result.append(
            {
                "id": el.element_id,
                "content": el.text or "",
                "left_ids": el.left_elem_ids,
                "right_ids": el.right_elem_ids,
                "top_ids": el.top_elem_ids,
                "bottom_ids": el.bottom_elem_ids,
            }
        )
    return result


def parse_screenshot(image_base64: Optional[str]) -> List[UIElement]:
    """
    Call the local OmniParser V2 API and return HAJIMI-style UIElement list.

    Delegates to parse_screenshot_full() to avoid code duplication.
    """
    return parse_screenshot_full(image_base64).elements


def parse_screenshot_full(
    image_base64: Optional[str], compute_spatial: bool = True
) -> ParseResult:
    """
    Call the local OmniParser V2 API and return a full ParseResult with metadata.

    Args:
        image_base64: Base64 image, with or without a data URI prefix.
        compute_spatial: If True, compute spatial relations (left/right/top/bottom).
                         Set to False for performance-sensitive callers that don't
                         need spatial relations (e.g., repeated calls in agent loop).

    Returns:
        ParseResult with elements, annotated_image, reference_resolution, detection_meta.
        Returns an empty ParseResult if no image is provided or parsing fails.
    """
    payload_base64 = _clean_base64(image_base64)
    if not payload_base64:
        return ParseResult()

    url = f"{_OMNIPARSER_URL}/parse/"
    payload = {"base64_image": payload_base64}

    latency_ms = 0
    last_exc = None
    for attempt in range(_OMNIPARSER_RETRY + 1):
        if attempt > 0:
            time.sleep(_OMNIPARSER_RETRY_DELAY)
        try:
            t_start = time.time()
            with httpx.Client(timeout=_OMNIPARSER_TIMEOUT) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                latency_ms = int((time.time() - t_start) * 1000)
                break  # success, exit retry loop
        except Exception as exc:
            last_exc = exc
            print(
                f"[OmniParser Client] attempt {attempt+1}/{_OMNIPARSER_RETRY+1} failed: {exc}"
            )
    else:
        # All retries exhausted
        print(f"[OmniParser Client] all retries exhausted: {last_exc}")
        return ParseResult()

    if data.get("error"):
        print(f"[OmniParser Client] parser returned error: {data['error']}")
        return ParseResult()

    raw_elements = data.get("parsed_content_list") or data.get("elements") or []

    # If OmniParser returned all None IDs, assign sequential ones
    all_none = all(
        isinstance(e, dict) and e.get("id") is None
        for e in raw_elements
        if isinstance(e, dict)
    )

    reference_resolution = None
    # Try PIL decode first to get image dimensions for bbox normalization
    try:
        raw = base64.b64decode(payload_base64)
        with Image.open(io.BytesIO(raw)) as img:
            reference_resolution = [img.width, img.height]
    except Exception:
        reference_resolution = [1920, 1080]

    elements: List[UIElement] = []
    seq = 1
    for item in raw_elements:
        if not isinstance(item, dict):
            continue
        bbox_raw = item.get("bbox")
        if not bbox_raw or len(bbox_raw) != 4:
            continue

        # OmniParser returns normalized 0-1 bbox. Convert to pixel bbox.
        x1, y1, x2, y2 = [float(v) for v in bbox_raw]
        if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.0:
            ref_w = reference_resolution[0]
            ref_h = reference_resolution[1]
            x1, x2 = int(x1 * ref_w), int(x2 * ref_w)
            y1, y2 = int(y1 * ref_h), int(y2 * ref_h)

        # Skip degenerate [0,0,0,0] bboxes
        if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
            continue

        raw_id = item.get("id")
        if raw_id is not None:
            element_id = str(raw_id)  # strip ~ prefix — was: f"~{raw_id}"
        elif all_none:
            element_id = str(seq)  # strip ~ prefix — was: f"~{seq}"
            seq += 1
        else:
            element_id = "?"

        center = item.get("center") or [(x1 + x2) / 2.0, (y1 + y2) / 2.0]
        center_int = [int(center[0]), int(center[1])]

        raw_type = item.get("element_type", item.get("type", "other"))
        allowed_types = {
            "button",
            "input",
            "icon",
            "menu",
            "checkbox",
            "dropdown",
            "text",
            "other",
        }
        element_type = raw_type if raw_type in allowed_types else "other"

        # Use OmniParser center if available, else bbox midpoint
        center_int = [int((x1 + x2) / 2), int((y1 + y2) / 2)]

        elements.append(
            UIElement(
                element_id=element_id,
                bbox=[x1, y1, x2, y2],
                element_type=element_type,
                text=item.get("text", "") or "",
                confidence=float(item.get("confidence", 1.0)),
                center=center_int,
            )
        )

    # ── Compute spatial relations (left/right/top/bottom neighbors) ──
    if compute_spatial:
        _compute_spatial_relations(elements)

    # ── 提取 SoM 标注图 ──
    annotated_image = None
    for key in (
        "som_image_base64",
        "som_image",
        "som_base64",
        "annotated_image",
        "labeled_image",
    ):
        val = data.get(key)
        if isinstance(val, str) and val:
            annotated_image = _compress_som_image(val)
            break

    # ── 提取 / 推导 reference_resolution ──
    reference_resolution = None
    # 优先从 OmniParser 响应取
    for w_key, h_key in (
        ("width", "height"),
        ("image_width", "image_height"),
        ("img_width", "img_height"),
    ):
        w = data.get(w_key)
        h = data.get(h_key)
        if isinstance(w, (int, float)) and isinstance(h, (int, float)):
            reference_resolution = [int(w), int(h)]
            break

    # 回退到 PIL 解码
    if reference_resolution is None:
        reference_resolution = _decode_image_resolution(payload_base64)

    # ── 检测元信息 ──
    detection_meta = {
        "latency_ms": latency_ms,
        "element_count": len(elements),
        "backend": "local_omniparser",
    }

    return ParseResult(
        elements=elements,
        annotated_image=annotated_image,
        reference_resolution=reference_resolution,
        detection_meta=detection_meta,
    )
