"""截图物理像素坐标 → Qt 覆盖层逻辑坐标。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.screen_utils import get_screen_metrics


def _metrics_or_default(metrics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return metrics if metrics else get_screen_metrics()


def capture_to_logical_bbox(
    bbox: List[int],
    capture_w: int,
    capture_h: int,
    metrics: Optional[Dict[str, Any]] = None,
) -> List[int]:
    if len(bbox) != 4:
        return bbox
    m = _metrics_or_default(metrics)
    log_w, log_h = int(m["logical_w"]), int(m["logical_h"])
    phys_w, phys_h = int(m["physical_w"]), int(m["physical_h"])
    dpr = float(m.get("dpr") or 1.0)

    x1, y1, x2, y2 = bbox

    # mss 截图通常为物理像素；Qt 覆盖层为逻辑坐标
    if abs(capture_w - phys_w) <= 4 and abs(capture_h - phys_h) <= 4:
        return [int(round(x1 / dpr)), int(round(y1 / dpr)),
                int(round(x2 / dpr)), int(round(y2 / dpr))]

    if abs(capture_w - log_w) <= 4 and abs(capture_h - log_h) <= 4:
        return [int(x1), int(y1), int(x2), int(y2)]

    # 其它尺寸：线性缩放到逻辑分辨率
    sx, sy = log_w / max(capture_w, 1), log_h / max(capture_h, 1)
    return [int(round(x1 * sx)), int(round(y1 * sy)),
            int(round(x2 * sx)), int(round(y2 * sy))]


def capture_to_logical_point(
    pt: List[int],
    capture_w: int,
    capture_h: int,
    metrics: Optional[Dict[str, Any]] = None,
) -> List[int]:
    if len(pt) != 2:
        return pt
    bbox = capture_to_logical_bbox(
        [pt[0], pt[1], pt[0], pt[1]], capture_w, capture_h, metrics
    )
    return [bbox[0], bbox[1]]


def adapt_annotation_to_logical(
    annotation: Optional[Dict],
    capture_size: Tuple[int, int],
    ref_size: Tuple[int, int],
    metrics: Optional[Dict[str, Any]] = None,
) -> Optional[Dict]:
    """参考分辨率 → 截图像素 → 覆盖层逻辑坐标。"""
    if not annotation:
        return annotation

    from core.coordinate_mapper import adapt_annotation

    cap_w, cap_h = capture_size
    ref_w, ref_h = ref_size
    # 先映射到与截图一致的像素空间
    in_capture = adapt_annotation(annotation, cap_w, cap_h, ref_w, ref_h)
    if not in_capture:
        return in_capture

    out = dict(in_capture)
    bbox = out.get("highlight_bbox")
    if bbox and len(bbox) == 4:
        out["highlight_bbox"] = capture_to_logical_bbox(bbox, cap_w, cap_h, metrics)
    for key in ("arrow_from", "arrow_to", "label_position"):
        pt = out.get(key)
        if pt and len(pt) == 2:
            out[key] = capture_to_logical_point(pt, cap_w, cap_h, metrics)
    return out
