"""
OmniParser HTTP client — GPU API v2 (:9800) and legacy omniparserserver (:8002).

GPU API contract (B端 omniparser_api):
  POST /parse/  {"base64_image": "..."}
  → parsed_content_list, som_image_base64, latency_ms, device
"""
import base64
import io
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import httpx

from server.config import reload_settings, settings
from server.models.schemas import UIElement

_DATA_URI_RE = re.compile(r"^data:image/\w+;base64,")


def _omni_config() -> tuple[str, int, int, float, int]:
    """Read OmniParser URL/timeouts at call time (reload server/.env)."""
    reload_settings()
    url = settings.OMNIPARSER_URL.rstrip("/")
    timeout = settings.OMNIPARSER_TIMEOUT
    retry = settings.OMNIPARSER_RETRY
    retry_delay = settings.OMNIPARSER_RETRY_DELAY
    max_side = settings.OMNIPARSER_LOCAL_MAX_SIDE
    if getattr(settings, "LLM_SPEED_MODE", "fast") == "fast":
        fast_side = getattr(settings, "OMNIPARSER_FAST_MAX_SIDE", 720)
        max_side = min(max_side, fast_side)
        fast_timeout = getattr(settings, "OMNIPARSER_FAST_TIMEOUT", 30)
        timeout = min(timeout, fast_timeout)
    return url, timeout, retry, retry_delay, max_side


def _clean_base64(image_base64: Optional[str]) -> Optional[str]:
    if not image_base64:
        return None
    cleaned = _DATA_URI_RE.sub("", image_base64)
    return cleaned.strip().replace("\n", "").replace("\r", "")


def _maybe_downscale_b64(
    payload_base64: str, max_side: int
) -> Tuple[str, Optional[List[int]], Optional[List[int]]]:
    """Return (base64, original_size, sent_size) or unchanged on failure."""
    try:
        from PIL import Image

        raw = base64.b64decode(payload_base64)
        with Image.open(io.BytesIO(raw)) as img:
            original = [img.width, img.height]
            w, h = img.width, img.height
            longest = max(w, h)
            if longest <= max_side:
                return payload_base64, original, original
            ratio = max_side / longest
            new_w, new_h = int(w * ratio), int(h * ratio)
            work = img.convert("RGB") if img.mode != "RGB" else img.copy()
            work = work.resize((new_w, new_h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            work.save(buf, format="PNG")
            sent = [new_w, new_h]
            return base64.b64encode(buf.getvalue()).decode("ascii"), original, sent
    except Exception as exc:
        print(f"[OmniParser Client] downscale skipped: {exc}")
        return payload_base64, None, None


def _decode_image_resolution(payload_base64: str) -> Optional[List[int]]:
    try:
        from PIL import Image

        raw = base64.b64decode(payload_base64)
        with Image.open(io.BytesIO(raw)) as img:
            return [img.width, img.height]
    except Exception:
        return None


def _parse_endpoints(base_url: str) -> List[str]:
    base = base_url.rstrip("/")
    return [f"{base}/parse/", f"{base}/parse"]


def _parse_payloads(b64: str) -> List[dict]:
    """GPU API v2 first; legacy omniparserserver fallback."""
    return [
        {"base64_image": b64},
        {"image": b64},
    ]


def _raw_elements_from_response(data: dict) -> list:
    raw = data.get("parsed_content_list") or data.get("elements") or []
    return raw if isinstance(raw, list) else []


def _normalize_element_id(raw_id) -> str:
    if raw_id is None:
        return "~?"
    text = str(raw_id).strip()
    if text.startswith("~"):
        return text
    return f"~{text}"


def _item_to_ui_element(
    item: dict,
    *,
    img_w: int = 0,
    img_h: int = 0,
    index: int = 0,
) -> Optional[UIElement]:
    if not isinstance(item, dict):
        return None
    bbox = item.get("bbox")
    if not bbox or len(bbox) != 4:
        return None

    raw_id = item.get("element_id", item.get("id"))
    element_id = f"~{index + 1}" if raw_id is None else _normalize_element_id(raw_id)

    vals = [float(v) for v in bbox]
    if img_w > 0 and img_h > 0 and max(vals) <= 1.0 and min(vals) >= 0:
        x1 = int(vals[0] * img_w)
        y1 = int(vals[1] * img_h)
        x2 = int(vals[2] * img_w)
        y2 = int(vals[3] * img_h)
    else:
        x1, y1, x2, y2 = (int(v) for v in vals)

    center_raw = item.get("center")
    if (
        center_raw
        and len(center_raw) >= 2
        and not (center_raw[0] == 0 and center_raw[1] == 0)
    ):
        cx, cy = float(center_raw[0]), float(center_raw[1])
        if img_w > 0 and img_h > 0 and max(abs(cx), abs(cy)) <= 1.0:
            center = [int(cx * img_w), int(cy * img_h)]
        else:
            center = [int(cx), int(cy)]
    else:
        center = [(x1 + x2) // 2, (y1 + y2) // 2]

    raw_type = item.get("element_type") or item.get("type") or "other"
    allowed_types = {
        "button", "input", "icon", "menu", "checkbox", "dropdown", "text", "other",
    }
    element_type = raw_type if raw_type in allowed_types else "other"

    return UIElement(
        element_id=element_id,
        bbox=[x1, y1, x2, y2],
        element_type=element_type,
        text=item.get("text", "") or item.get("content", "") or "",
        confidence=float(item.get("confidence", 1.0)),
        center=center,
    )


def _annotated_image_from_response(data: dict) -> Optional[str]:
    for key in (
        "som_image_base64",
        "annotated_image",
        "labeled_image",
        "som_image",
        "som_base64",
    ):
        val = data.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def _resolution_from_response(data: dict, payload_base64: str) -> Optional[List[int]]:
    image_size = data.get("image_size")
    if isinstance(image_size, dict):
        w = image_size.get("width")
        h = image_size.get("height")
        if isinstance(w, (int, float)) and isinstance(h, (int, float)):
            return [int(w), int(h)]

    for w_key, h_key in (
        ("width", "height"),
        ("image_width", "image_height"),
        ("img_width", "img_height"),
    ):
        w = data.get(w_key)
        h = data.get(h_key)
        if isinstance(w, (int, float)) and isinstance(h, (int, float)):
            return [int(w), int(h)]

    return _decode_image_resolution(payload_base64)


@dataclass
class ParseResult:
    """Full result from OmniParser parse call."""
    elements: List[UIElement] = field(default_factory=list)
    annotated_image: Optional[str] = None
    reference_resolution: Optional[List[int]] = None
    detection_meta: Optional[dict] = None


def parse_screenshot(image_base64: Optional[str]) -> List[UIElement]:
    return parse_screenshot_full(image_base64).elements


def parse_screenshot_full(image_base64: Optional[str]) -> ParseResult:
    payload_base64 = _clean_base64(image_base64)
    if not payload_base64:
        return ParseResult()

    omni_url, omni_timeout, omni_retry, omni_retry_delay, max_side = _omni_config()
    payload_base64, original_size, sent_size = _maybe_downscale_b64(
        payload_base64, max_side
    )
    if original_size and sent_size and original_size != sent_size:
        print(
            f"[OmniParser Client] downscale {original_size[0]}x{original_size[1]}"
            f" -> {sent_size[0]}x{sent_size[1]} max_side={max_side}"
        )

    last_exc = None
    data = None
    latency_ms = 0
    t_start = time.time()
    print(
        f"[OmniParser Client] POST {omni_url}/parse/ timeout={omni_timeout}s "
        f"retry={omni_retry}"
    )

    for attempt in range(omni_retry + 1):
        if attempt > 0:
            time.sleep(omni_retry_delay)
        try:
            with httpx.Client(timeout=omni_timeout) as client:
                for url in _parse_endpoints(omni_url):
                    for payload in _parse_payloads(payload_base64):
                        response = client.post(url, json=payload)
                        if response.status_code in (404, 405, 422):
                            continue
                        response.raise_for_status()
                        data = response.json()
                        break
                    if data is not None:
                        break
            if data is not None:
                break
            raise httpx.HTTPError("no compatible /parse endpoint accepted request")
        except Exception as exc:
            last_exc = exc
            print(
                f"[OmniParser Client] attempt {attempt + 1}/{omni_retry + 1} failed: {exc}"
            )
    else:
        print(f"[OmniParser Client] all retries exhausted: {last_exc}")
        return ParseResult()

    latency_ms = int((time.time() - t_start) * 1000)
    print(
        f"[OmniParser Client] parse done in {latency_ms}ms url={omni_url}"
    )

    if not isinstance(data, dict):
        return ParseResult()

    if data.get("error"):
        print(f"[OmniParser Client] parser returned error: {data['error']}")
        return ParseResult()

    elements: List[UIElement] = []
    resolution = _resolution_from_response(data, payload_base64) or sent_size or [960, 540]
    img_w = int(resolution[0]) if resolution else 0
    img_h = int(resolution[1]) if len(resolution or []) > 1 else 0
    for i, item in enumerate(_raw_elements_from_response(data)):
        elem = _item_to_ui_element(item, img_w=img_w, img_h=img_h, index=i)
        if elem is not None:
            elements.append(elem)

    detection_meta = {
        "latency_ms": data.get("latency_ms", latency_ms),
        "parse_latency_ms": latency_ms,
        "element_count": len(elements),
        "backend": data.get("backend", "local_omniparser"),
        "device": data.get("device"),
        "omniparser_url": omni_url,
        "original_size": original_size,
        "sent_size": sent_size,
    }

    return ParseResult(
        elements=elements,
        annotated_image=_annotated_image_from_response(data),
        reference_resolution=_resolution_from_response(data, payload_base64),
        detection_meta=detection_meta,
    )
