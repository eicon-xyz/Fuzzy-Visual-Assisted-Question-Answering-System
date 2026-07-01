"""屏幕坐标自适应：将 A 端参考分辨率下的 bbox 缩放到实际截图尺寸。"""
from typing import Dict, List, Optional, Tuple

REF_W = 1920
REF_H = 1080


def scale_value(value: float, src_size: int, dst_size: int) -> int:
    if src_size <= 0:
        return int(value)
    return int(round(value * dst_size / src_size))


def scale_bbox(
    bbox: List[int],
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
) -> List[int]:
    if len(bbox) != 4:
        return bbox
    x1, y1, x2, y2 = bbox
    return [
        scale_value(x1, src_w, dst_w),
        scale_value(y1, src_h, dst_h),
        scale_value(x2, src_w, dst_w),
        scale_value(y2, src_h, dst_h),
    ]


def scale_point(
    pt: List[int],
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
) -> List[int]:
    if len(pt) != 2:
        return pt
    return [
        scale_value(pt[0], src_w, dst_w),
        scale_value(pt[1], src_h, dst_h),
    ]


def adapt_annotation(
    annotation: Optional[Dict],
    screen_w: int,
    screen_h: int,
    ref_w: int = REF_W,
    ref_h: int = REF_H,
) -> Optional[Dict]:
    """将 annotation 坐标从参考分辨率映射到实际屏幕物理像素。"""
    if not annotation:
        return annotation

    if screen_w == ref_w and screen_h == ref_h:
        return dict(annotation)

    adapted = dict(annotation)
    bbox = adapted.get("highlight_bbox")
    if bbox and len(bbox) == 4:
        adapted["highlight_bbox"] = scale_bbox(bbox, ref_w, ref_h, screen_w, screen_h)

    for key in ("arrow_from", "arrow_to", "label_position"):
        pt = adapted.get(key)
        if pt and len(pt) == 2:
            adapted[key] = scale_point(pt, ref_w, ref_h, screen_w, screen_h)

    return adapted


def needs_scaling(screen_w: int, screen_h: int, ref_w: int = REF_W, ref_h: int = REF_H) -> bool:
    return screen_w != ref_w or screen_h != ref_h
