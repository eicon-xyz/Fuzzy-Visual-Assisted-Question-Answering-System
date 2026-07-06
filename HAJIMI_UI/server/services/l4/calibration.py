"""
L4 坐标校准：Vision 在「上传图空间」出点，映射到「原始 capture 空间」供 B 端 overlay。
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from server.models.schemas import Annotation
from server.services.l4.types import L4ScreenContext


def scale_annotation_to_capture(
    annotation: Annotation,
    upload_size: Tuple[int, int],
    capture_size: Tuple[int, int],
) -> Annotation:
    """将 upload 像素空间下的 annotation 线性映射到 capture 像素空间。"""
    up_w, up_h = upload_size
    cap_w, cap_h = capture_size
    if up_w == cap_w and up_h == cap_h:
        return annotation

    def _scale_pt(pt: Optional[List[int]]) -> Optional[List[int]]:
        if not pt or len(pt) != 2:
            return pt
        return [
            int(round(pt[0] * cap_w / max(up_w, 1))),
            int(round(pt[1] * cap_h / max(up_h, 1))),
        ]

    def _scale_bbox(bbox: Optional[List[int]]) -> Optional[List[int]]:
        if not bbox or len(bbox) != 4:
            return bbox
        x1, y1, x2, y2 = bbox
        return [
            int(round(x1 * cap_w / max(up_w, 1))),
            int(round(y1 * cap_h / max(up_h, 1))),
            int(round(x2 * cap_w / max(up_w, 1))),
            int(round(y2 * cap_h / max(up_h, 1))),
        ]

    return Annotation(
        type=annotation.type,
        arrow_from=_scale_pt(annotation.arrow_from),
        arrow_to=_scale_pt(annotation.arrow_to),
        highlight_bbox=_scale_bbox(annotation.highlight_bbox),
        label_position=_scale_pt(annotation.label_position),
        label_text=annotation.label_text,
    )


def resolve_coordinate_space(
    ctx: L4ScreenContext,
    upload_w: int,
    upload_h: int,
) -> Tuple[int, int, Optional[List[int]]]:
    """
    Returns:
        (coord_w, coord_h, reference_resolution for B-end)
    """
    ctx.upload_size = [upload_w, upload_h]
    ref = ctx.reference_resolution
    if ctx.capture_size and len(ctx.capture_size) >= 2:
        return upload_w, upload_h, ref
    return upload_w, upload_h, [upload_w, upload_h]


def finalize_l4_annotation(
    annotation: Annotation,
    ctx: L4ScreenContext,
    upload_w: int,
    upload_h: int,
) -> Tuple[Annotation, Optional[List[int]]]:
    """upload 空间 annotation → capture 空间（若 B 端提供了 capture_size）。"""
    ref = ctx.reference_resolution
    if (
        ctx.capture_size
        and len(ctx.capture_size) >= 2
        and (ctx.capture_size[0] != upload_w or ctx.capture_size[1] != upload_h)
    ):
        cap = (int(ctx.capture_size[0]), int(ctx.capture_size[1]))
        ann = scale_annotation_to_capture(
            annotation, (upload_w, upload_h), cap
        )
        return ann, [cap[0], cap[1]]
    return annotation, ref or [upload_w, upload_h]
