"""可插拔 UI 元素检测 — Replicate 或本地 omniparserserver。"""

from __future__ import annotations

import ast
import base64
import os
import re
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image

from server.config import settings
from server.models.schemas import UIElement

_TYPE_MAP = {
    "button": "button",
    "input": "input",
    "icon": "icon",
    "menu": "menu",
    "checkbox": "checkbox",
    "dropdown": "dropdown",
    "text": "text",
    "link": "button",
    "image": "icon",
    "unknown": "other",
}

OMNIPARSER_MODEL = (
    "microsoft/omniparser-v2:"
    "49cf3d41b8d3aca1360514e83be4c97131ce8f0d99abfc365526d8384caa88df"
)


@dataclass
class DetectionResult:
    elements: List[UIElement]
    reference_resolution: Tuple[int, int]
    latency_ms: int
    backend: str


class DetectorError(Exception):
    """检测器调用失败。"""


_active_backend: Optional[str] = None
_active_url: Optional[str] = None
_active_device: Optional[str] = None


def probe_omniparser_url(base_url: str) -> Tuple[bool, Optional[str]]:
    """探测 omniparserserver /probe/，返回 (reachable, device)。"""
    url = (base_url or "").rstrip("/")
    if not url:
        return False, None
    try:
        timeout = float(settings.OMNIPARSER_PROBE_TIMEOUT)
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{url}/probe/")
            if resp.status_code != 200:
                return False, None
            try:
                data = resp.json()
            except Exception:
                return True, None
            device = data.get("device")
            if data.get("ready") is False:
                return False, device
            return True, device
    except Exception:
        return False, None


def resolve_auto_backend(force: bool = False) -> Tuple[str, str, Optional[str]]:
    """
    解析 auto 模式实际后端。
    返回 (backend_label, base_url, device)。
    """
    global _active_backend, _active_url, _active_device
    if not force and _active_backend and _active_url:
        return _active_backend, _active_url, _active_device

    candidates: List[Tuple[str, str]] = []
    gpu = (settings.OMNIPARSER_GPU_URL or "").strip().rstrip("/")
    local = (settings.OMNIPARSER_LOCAL_URL or "").strip().rstrip("/")
    if gpu:
        candidates.append(("local_omniparser", gpu))
    if local and local != gpu:
        candidates.append(("local_omniparser", local))

    for label, url in candidates:
        ready, device = probe_omniparser_url(url)
        if ready:
            _active_backend = label
            _active_url = url
            _active_device = device or "cpu"
            return _active_backend, _active_url, _active_device

    if settings.DETECTOR_AUTO_FALLBACK_REPLICATE and settings.REPLICATE_API_TOKEN:
        _active_backend = "replicate_omniparser"
        _active_url = ""
        _active_device = "cloud"
        return _active_backend, _active_url, _active_device

    _active_backend = None
    _active_url = None
    _active_device = None
    raise DetectorError(
        "auto detector: no reachable OmniParser (check OMNIPARSER_GPU_URL / OMNIPARSER_LOCAL_URL)"
    )


def get_detector_health_info() -> Dict[str, Any]:
    """供 /health 使用的检测器状态。"""
    backend = settings.DETECTOR_BACKEND
    info: Dict[str, Any] = {
        "detector_backend": backend,
        "detector_active": None,
        "detector_device": None,
        "omniparser_url": None,
        "omniparser_ready": None,
    }
    if backend == "replicate_omniparser":
        info["detector_active"] = "replicate_omniparser"
        info["detector_device"] = "cloud"
        info["omniparser_ready"] = bool(settings.REPLICATE_API_TOKEN)
        return info
    if backend == "local_omniparser":
        url = (settings.OMNIPARSER_LOCAL_URL or "").rstrip("/")
        ready, device = probe_omniparser_url(url) if url else (False, None)
        info["detector_active"] = "local_omniparser"
        info["detector_device"] = device
        info["omniparser_url"] = url or None
        info["omniparser_ready"] = ready
        return info
    if backend == "auto":
        try:
            active, url, device = resolve_auto_backend(force=True)
            ready, _ = probe_omniparser_url(url) if url else (False, None)
            info["detector_active"] = active
            info["detector_device"] = device
            info["omniparser_url"] = url or None
            info["omniparser_ready"] = (
                ready if url else bool(settings.REPLICATE_API_TOKEN)
            )
        except DetectorError:
            info["detector_active"] = None
            info["detector_device"] = None
            info["omniparser_url"] = None
            info["omniparser_ready"] = False
        return info
    return info


def detect(pil_image: Image.Image, backend: Optional[str] = None) -> DetectionResult:
    backend = backend or settings.DETECTOR_BACKEND
    if backend == "auto":
        active, url, _device = resolve_auto_backend()
        if active == "replicate_omniparser":
            return _detect_replicate_omniparser(pil_image)
        return _detect_local_omniparser(pil_image, base_url=url)
    if backend == "replicate_omniparser":
        return _detect_replicate_omniparser(pil_image)
    if backend == "local_omniparser":
        return _detect_local_omniparser(pil_image)
    raise DetectorError(f"unsupported detector backend: {backend}")


def _pil_to_png_base64(pil_image: Image.Image) -> str:
    buffer = BytesIO()
    pil_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _maybe_downscale(
    pil_image: Image.Image, max_side: int
) -> Tuple[Image.Image, float, float]:
    w, h = pil_image.width, pil_image.height
    longest = max(w, h)
    if longest <= max_side:
        return pil_image, 1.0, 1.0
    ratio = max_side / longest
    new_w, new_h = int(w * ratio), int(h * ratio)
    resized = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return resized, w / new_w, h / new_h


def _scale_elements_to_original(
    elements: List[UIElement], scale_x: float, scale_y: float
) -> List[UIElement]:
    scaled: List[UIElement] = []
    for el in elements:
        x1, y1, x2, y2 = el.bbox
        bbox = [
            int(x1 * scale_x),
            int(y1 * scale_y),
            int(x2 * scale_x),
            int(y2 * scale_y),
        ]
        cx = (bbox[0] + bbox[2]) // 2
        cy = (bbox[1] + bbox[3]) // 2
        scaled.append(
            UIElement(
                element_id=el.element_id,
                bbox=bbox,
                element_type=el.element_type,
                text=el.text,
                confidence=el.confidence,
                center=[cx, cy],
            )
        )
    return scaled


def _detect_local_omniparser(
    pil_image: Image.Image, base_url: Optional[str] = None
) -> DetectionResult:
    base_url = (base_url or settings.OMNIPARSER_LOCAL_URL or "").rstrip("/")
    if not base_url:
        raise DetectorError("OMNIPARSER_LOCAL_URL not configured")

    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")

    work_image, scale_x, scale_y = _maybe_downscale(
        pil_image, settings.OMNIPARSER_LOCAL_MAX_SIDE
    )

    t0 = time.perf_counter()
    b64 = _pil_to_png_base64(work_image)
    try:
        timeout = httpx.Timeout(
            10.0,
            read=float(settings.OMNIPARSER_LOCAL_TIMEOUT),
            write=30.0,
            pool=10.0,
        )
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{base_url}/parse/",
                json={"base64_image": b64},
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response else str(exc)
        try:
            err_json = exc.response.json()
            if isinstance(err_json, dict) and err_json.get("detail"):
                detail = str(err_json["detail"])[:500]
        except Exception:
            pass
        if exc.response.status_code == 500:
            detail += (
                " (hint: 可能为空白屏/无 UI 元素、内存不足或上一次解析尚未结束；"
                "请重启 OmniParser 或运行 scripts\\stop_all.bat 后 scripts\\start_all.bat)"
            )
        raise DetectorError(
            f"local OmniParser HTTP {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.ConnectError as exc:
        raise DetectorError(
            f"local OmniParser not reachable at {base_url} — run scripts\\start_omniparser.bat"
        ) from exc
    except Exception as exc:
        raise DetectorError(f"local OmniParser call failed: {exc}") from exc

    parsed = _parse_local_output(payload)
    elements = _normalize_elements(parsed, work_image.width, work_image.height)
    if scale_x != 1.0 or scale_y != 1.0:
        elements = _scale_elements_to_original(elements, scale_x, scale_y)
    elements = _filter_elements(elements)

    if not elements and settings.ALLOW_DETECTOR_FALLBACK:
        elements = _fallback_preset_elements(pil_image.width, pil_image.height)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return DetectionResult(
        elements=elements,
        reference_resolution=(pil_image.width, pil_image.height),
        latency_ms=latency_ms,
        backend="local_omniparser",
    )


def _detect_replicate_omniparser(pil_image: Image.Image) -> DetectionResult:
    if not settings.REPLICATE_API_TOKEN:
        raise DetectorError("REPLICATE_API_TOKEN not configured")

    import replicate

    os.environ.setdefault("REPLICATE_API_TOKEN", settings.REPLICATE_API_TOKEN)

    t0 = time.perf_counter()
    # Replicate HTTP API 需可 JSON 序列化的 image 字段：data URI 或 file-like
    image_input = f"data:image/png;base64,{_pil_to_png_base64(pil_image)}"

    model = settings.OMNIPARSER_MODEL or OMNIPARSER_MODEL
    try:
        output = replicate.run(
            model,
            input={
                "image": image_input,
                "imgsz": settings.OMNIPARSER_IMGSZ,
                "box_threshold": settings.OMNIPARSER_BOX_THRESHOLD,
                "iou_threshold": settings.OMNIPARSER_IOU_THRESHOLD,
            },
        )
    except Exception as exc:
        raise DetectorError(f"OmniParser replicate call failed: {exc}") from exc

    parsed = _parse_replicate_output(output)
    elements = _normalize_elements(parsed, pil_image.width, pil_image.height)
    elements = _filter_elements(elements)

    if not elements and settings.ALLOW_DETECTOR_FALLBACK:
        elements = _fallback_preset_elements(pil_image.width, pil_image.height)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return DetectionResult(
        elements=elements,
        reference_resolution=(pil_image.width, pil_image.height),
        latency_ms=latency_ms,
        backend="replicate_omniparser",
    )


def _parse_local_output(payload) -> List[dict]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("parsed_content_list") or payload.get("parsed_content")
    if raw is None:
        return _parse_replicate_output(payload)
    return _coerce_local_items(raw)


def _coerce_local_items(data) -> List[dict]:
    if not data:
        return []
    if not isinstance(data, list):
        return []

    items: List[dict] = []
    for entry in data:
        if isinstance(entry, dict):
            items.append(entry)
            continue
        if not isinstance(entry, str):
            continue
        # OmniParser 有时返回 "icon 0: {'bbox': [...], 'type': '...', ...}" 字符串
        m = re.search(r"\{.*\}", entry, re.DOTALL)
        if not m:
            continue
        try:
            parsed = ast.literal_eval(m.group(0))
            if isinstance(parsed, dict):
                items.append(parsed)
        except (SyntaxError, ValueError):
            continue
    return items


def _parse_replicate_output(output) -> List[dict]:
    if output is None:
        return []

    if isinstance(output, dict):
        parsed = (
            output.get("parsed_content")
            or output.get("boxes")
            or output.get("elements")
        )
        if parsed is not None:
            return _coerce_item_list(parsed)
        return _coerce_item_list(output)

    if isinstance(output, list):
        return _coerce_item_list(output)

    if isinstance(output, str):
        return []

    return []


def _coerce_item_list(data) -> List[dict]:
    if not data:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _normalize_elements(
    raw_items: List[dict], img_w: int, img_h: int
) -> List[UIElement]:
    candidates = []
    for item in raw_items:
        bbox = _normalize_bbox(item.get("bbox") or item.get("box"), img_w, img_h)
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        raw_type = str(item.get("type") or item.get("element_type") or "other").lower()
        element_type = _TYPE_MAP.get(raw_type, "other")
        text = str(item.get("text") or item.get("content") or "").strip()
        try:
            confidence = float(item.get("confidence", 0.85))
        except (TypeError, ValueError):
            confidence = 0.85
        confidence = max(0.0, min(1.0, confidence))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        area = max(1, (x2 - x1) * (y2 - y1))
        candidates.append(
            {
                "bbox": bbox,
                "element_type": element_type,
                "text": text,
                "confidence": confidence,
                "center": [cx, cy],
                "area": area,
                "y1": y1,
                "x1": x1,
            }
        )

    candidates.sort(key=lambda c: (c["y1"], c["x1"]))

    elements: List[UIElement] = []
    for i, c in enumerate(candidates):
        elements.append(
            UIElement(
                element_id=f"~{i + 1}",
                bbox=c["bbox"],
                element_type=c["element_type"],
                text=c["text"],
                confidence=c["confidence"],
                center=c["center"],
            )
        )
    return elements


def _normalize_bbox(bbox, img_w: int, img_h: int) -> Optional[List[int]]:
    if not bbox or len(bbox) != 4:
        return None
    try:
        vals = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None

    if max(vals) <= 1.0 and min(vals) >= 0.0:
        x1 = int(vals[0] * img_w)
        x2 = int(vals[2] * img_w)
        y1 = int(vals[1] * img_h)
        y2 = int(vals[3] * img_h)
    else:
        x1, y1, x2, y2 = [int(round(v)) for v in vals]

    x1, x2 = sorted((max(0, x1), min(img_w, x2)))
    y1, y2 = sorted((max(0, y1), min(img_h, y2)))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return [x1, y1, x2, y2]


def _filter_elements(elements: List[UIElement]) -> List[UIElement]:
    max_n = settings.OMNIPARSER_MAX_ELEMENTS
    min_area = settings.OMNIPARSER_MIN_AREA
    filtered = []
    for el in elements:
        x1, y1, x2, y2 = el.bbox
        if (x2 - x1) * (y2 - y1) < min_area:
            continue
        filtered.append(el)
    return filtered[:max_n]


def _fallback_preset_elements(sw: int, sh: int) -> List[UIElement]:
    """检测失败时的 dev fallback（比例坐标）。"""

    def box(xr, yr, wr, hr):
        return [
            int(sw * xr),
            int(sh * yr),
            int(sw * (xr + wr)),
            int(sh * (yr + hr)),
        ]

    presets = [
        ("~1", box(0.12, 0.30, 0.10, 0.06), "icon", "preset-1"),
        ("~2", box(0.35, 0.04, 0.30, 0.05), "input", "preset-2"),
        ("~3", box(0.70, 0.50, 0.12, 0.06), "button", "preset-3"),
    ]
    out = []
    for eid, bbox, etype, text in presets:
        cx = (bbox[0] + bbox[2]) // 2
        cy = (bbox[1] + bbox[3]) // 2
        out.append(
            UIElement(
                element_id=eid,
                bbox=bbox,
                element_type=etype,
                text=text,
                confidence=0.5,
                center=[cx, cy],
            )
        )
    return out
