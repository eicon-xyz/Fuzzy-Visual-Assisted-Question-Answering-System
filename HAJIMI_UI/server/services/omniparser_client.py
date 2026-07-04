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

from server.config import settings
from server.models.schemas import UIElement


_OMNIPARSER_URL = settings.OMNIPARSER_URL.rstrip("/")
_OMNIPARSER_TIMEOUT = settings.OMNIPARSER_TIMEOUT
_OMNIPARSER_RETRY = getattr(settings, "OMNIPARSER_RETRY", 1)
_OMNIPARSER_RETRY_DELAY = getattr(settings, "OMNIPARSER_RETRY_DELAY", 3.0)

# Regex to strip data URI prefix, e.g. "data:image/png;base64,"
_DATA_URI_RE = re.compile(r"^data:image/\w+;base64,")


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


def parse_screenshot(image_base64: Optional[str]) -> List[UIElement]:
    """
    Call the local OmniParser V2 API and return HAJIMI-style UIElement list.

    Delegates to parse_screenshot_full() to avoid code duplication.
    """
    return parse_screenshot_full(image_base64).elements


def parse_screenshot_full(image_base64: Optional[str]) -> ParseResult:
    """
    Call the local OmniParser V2 API and return a full ParseResult with metadata.

    Args:
        image_base64: Base64 image, with or without a data URI prefix.

    Returns:
        ParseResult with elements, annotated_image, reference_resolution, detection_meta.
        Returns an empty ParseResult if no image is provided or parsing fails.
    """
    payload_base64 = _clean_base64(image_base64)
    if not payload_base64:
        return ParseResult()

    url = f"{_OMNIPARSER_URL}/parse"
    payload = {"image": payload_base64}

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
                break  # success, exit retry loop
        except Exception as exc:
            last_exc = exc
            print(f"[OmniParser Client] attempt {attempt+1}/{_OMNIPARSER_RETRY+1} failed: {exc}")
    else:
        # All retries exhausted
        latency_ms = int((time.time() - t_start) * 1000) if 't_start' in dir() else 0
        print(f"[OmniParser Client] all retries exhausted: {last_exc}")
        return ParseResult()

    if data.get("error"):
        print(f"[OmniParser Client] parser returned error: {data['error']}")
        return ParseResult()

    raw_elements = data.get("elements") or []

    elements: List[UIElement] = []
    for item in raw_elements:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        raw_id = item.get("id")
        element_id = f"~{raw_id}" if raw_id is not None else "~?"

        x1, y1, x2, y2 = bbox
        center = item.get("center") or [(x1 + x2) // 2, (y1 + y2) // 2]

        raw_type = item.get("type", "other")
        allowed_types = {"button", "input", "icon", "menu", "checkbox", "dropdown", "text", "other"}
        element_type = raw_type if raw_type in allowed_types else "other"

        elements.append(
            UIElement(
                element_id=element_id,
                bbox=bbox,
                element_type=element_type,
                text=item.get("text", "") or "",
                confidence=float(item.get("confidence", 1.0)),
                center=center,
            )
        )

    # ── 提取 SoM 标注图 ──
    annotated_image = None
    for key in ("annotated_image", "labeled_image", "som_image", "som_base64"):
        val = data.get(key)
        if isinstance(val, str) and val:
            annotated_image = val
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
