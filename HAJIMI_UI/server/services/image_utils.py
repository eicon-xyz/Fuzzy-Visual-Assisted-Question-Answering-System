"""Base64 / data-URI 截图解码。"""

import base64
import re
from io import BytesIO
from typing import Tuple

from PIL import Image

_DATA_URI_RE = re.compile(r"^data:image/[\w+.-]+;base64,", re.I)


def decode_image(image_b64: str) -> Tuple[Image.Image, int, int]:
    """解码 Base64 或 data:image/...;base64,... 为 RGB PIL 图像。"""
    if not image_b64 or not str(image_b64).strip():
        raise ValueError("empty image payload")

    raw = str(image_b64).strip()
    if _DATA_URI_RE.match(raw):
        raw = _DATA_URI_RE.sub("", raw)

    try:
        img_bytes = base64.b64decode(raw, validate=False)
    except Exception as exc:
        raise ValueError(f"invalid base64 image: {exc}") from exc

    img = Image.open(BytesIO(img_bytes)).convert("RGB")
    return img, img.width, img.height
