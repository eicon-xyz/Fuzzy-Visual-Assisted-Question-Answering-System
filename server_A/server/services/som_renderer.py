"""Set-of-Mark 标注图渲染。"""

import base64
from io import BytesIO
from typing import List

import cv2
import numpy as np
from PIL import Image

from server.models.schemas import UIElement

_COLOR_MAP = {
    "button": (0, 0, 255),
    "input": (0, 255, 0),
    "icon": (0, 255, 255),
    "menu": (255, 0, 255),
    "checkbox": (255, 255, 0),
    "dropdown": (255, 128, 0),
    "text": (200, 200, 200),
    "other": (128, 128, 255),
}


def render(pil_image: Image.Image, elements: List[UIElement]) -> Image.Image:
    cv_img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    for el in elements:
        x1, y1, x2, y2 = el.bbox
        color = _COLOR_MAP.get(el.element_type, (0, 0, 255))
        cv2.rectangle(cv_img, (x1, y1), (x2, y2), color, 2)

        label = el.element_id
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        label_x = x1
        label_y = y1 - th - 6
        if label_y < th + 4:
            label_y = y2 + th + 6
        cv2.rectangle(
            cv_img,
            (label_x, label_y - th - 4),
            (label_x + tw + 4, label_y + 4),
            (255, 255, 255),
            -1,
        )
        cv2.putText(
            cv_img,
            label,
            (label_x + 2, label_y - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
        )

    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))


def render_base64(pil_image: Image.Image, elements: List[UIElement]) -> str:
    annotated = render(pil_image, elements)
    buffer = BytesIO()
    annotated.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"
