"""
共享标注构建器
router.py 与 replanner.py 共用，消除重复代码。
"""
from typing import List, Optional

from server.models.schemas import UIElement, Annotation


def build_annotation(
    element: UIElement,
    annotation_type: str,
    label_text: str,
    arrow_offset_x: int = 150,
    arrow_offset_y: int = 100,
    label_offset_y: int = 44,
) -> Annotation:
    """为 UI 元素生成屏幕标注（箭头 + 高亮框 + 标签）。"""
    x1, y1, x2, y2 = element.bbox
    cx, cy = element.center or [(x1 + x2) / 2.0, (y1 + y2) / 2.0]

    return Annotation(
        type=annotation_type,
        arrow_from=[int(max(0, cx - arrow_offset_x)), int(max(0, cy - arrow_offset_y))],
        arrow_to=[int(cx), int(cy)],
        highlight_bbox=[int(v) for v in element.bbox],
        label_position=[int(x1), int(max(0, y1 - label_offset_y))],
        label_text=label_text,
    )
