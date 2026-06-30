"""
Local OmniParser V2 HTTP client.

The OmniParser API server is deployed separately (D:\\ominprester) and exposes
POST /parse, which returns structured UI elements for a base64-encoded image.
This module converts those elements into the HAJIMI UIElement schema.
"""
import re
from typing import List, Optional

import httpx

from server.config import settings
from server.models.schemas import UIElement


_OMNIPARSER_URL = settings.OMNIPARSER_URL.rstrip("/")
_OMNIPARSER_TIMEOUT = settings.OMNIPARSER_TIMEOUT

# Regex to strip data URI prefix, e.g. "data:image/png;base64,"
_DATA_URI_RE = re.compile(r"^data:image/\w+;base64,")


def _clean_base64(image_base64: Optional[str]) -> Optional[str]:
    if not image_base64:
        return None
    cleaned = _DATA_URI_RE.sub("", image_base64)
    # Remove any whitespace/newlines that may have been inserted by transport
    return cleaned.strip().replace("\n", "").replace("\r", "")


def parse_screenshot(image_base64: Optional[str]) -> List[UIElement]:
    """
    Call the local OmniParser V2 API and return HAJIMI-style UIElement list.

    Args:
        image_base64: Base64 image, with or without a data URI prefix.

    Returns:
        List of UIElement. Returns an empty list if no image is provided,
        the parser is unreachable, or parsing fails.
    """
    payload_base64 = _clean_base64(image_base64)
    if not payload_base64:
        return []

    url = f"{_OMNIPARSER_URL}/parse"
    payload = {"image": payload_base64}

    try:
        with httpx.Client(timeout=_OMNIPARSER_TIMEOUT) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        print(f"[OmniParser Client] parser unavailable or request failed: {exc}")
        return []

    if data.get("error"):
        print(f"[OmniParser Client] parser returned error: {data['error']}")
        return []

    raw_elements = data.get("elements") or []
    if not raw_elements:
        return []

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

        # Make sure element_type stays within the allowed schema values
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

    return elements
