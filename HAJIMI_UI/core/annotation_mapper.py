from typing import Dict, List, Optional, Tuple

from core.overlay_coords import adapt_annotation_to_logical


def to_overlay_items(
    annotation: Optional[Dict],
    step_index: int,
    screen_size: Tuple[int, int] = (1920, 1080),
    ref_size: Tuple[int, int] = (1920, 1080),
    screen_metrics: Optional[Dict] = None,
) -> List[Dict]:
    if not annotation:
        return []

    adapted = adapt_annotation_to_logical(
        annotation, screen_size, ref_size, screen_metrics
    )

    items = []
    bbox = adapted.get("highlight_bbox")
    if bbox and len(bbox) == 4:
        items.append({
            "type": "box",
            "rect": bbox,
            "label": str(step_index),
        })

    arrow_from = adapted.get("arrow_from")
    arrow_to = adapted.get("arrow_to")
    if arrow_from and arrow_to and len(arrow_from) == 2 and len(arrow_to) == 2:
        items.append({
            "type": "arrow",
            "from": arrow_from,
            "to": arrow_to,
        })

    return items


def ui_elements_to_inspect_items(
    elements: List[Dict],
    screen_size: Tuple[int, int] = (1920, 1080),
    screen_metrics: Optional[Dict] = None,
) -> List[Dict]:
    """检验模式：全量元素框（逻辑坐标）。"""
    from core.overlay_coords import capture_to_logical_bbox

    cap_w, cap_h = screen_size
    items = []
    for el in elements or []:
        bbox = el.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        logical_bbox = capture_to_logical_bbox(bbox, cap_w, cap_h, screen_metrics)
        eid = el.get("element_id", "")
        etype = el.get("element_type", "")
        text = (el.get("text") or "")[:16]
        label = eid
        if etype:
            label = f"{eid} {etype}"
        items.append({
            "type": "inspect_box",
            "rect": logical_bbox,
            "label": label,
            "detail": text,
        })
    return items
