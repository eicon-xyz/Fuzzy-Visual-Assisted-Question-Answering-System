from typing import Dict, List, Optional


def to_overlay_items(annotation: Optional[Dict], step_index: int) -> List[Dict]:
    if not annotation:
        return []

    items = []
    bbox = annotation.get("highlight_bbox")
    if bbox and len(bbox) == 4:
        items.append({
            "type": "box",
            "rect": bbox,
            "label": str(step_index),
        })

    arrow_from = annotation.get("arrow_from")
    arrow_to = annotation.get("arrow_to")
    if arrow_from and arrow_to and len(arrow_from) == 2 and len(arrow_to) == 2:
        items.append({
            "type": "arrow",
            "from": arrow_from,
            "to": arrow_to,
        })

    return items
