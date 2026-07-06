"""L4 图像工具。"""
from __future__ import annotations

import re

_DATA_URI_RE = re.compile(r"^data:image/[\w+.-]+;base64,", re.I)


def clean_base64(image: str) -> str:
    if not image:
        return ""
    text = image.strip()
    return _DATA_URI_RE.sub("", text)
