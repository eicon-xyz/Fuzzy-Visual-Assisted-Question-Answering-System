"""窗口 ROI 裁切 — Vision 回落时缩小上传区域。"""
from __future__ import annotations

import base64
import io
from typing import List, Optional, Tuple

from server.services.assist.config import ASSIST_ROI_VISION_FALLBACK


def crop_image_to_foreground_roi(
    image_b64: str,
    foreground_rect: Optional[List[int]],
    capture_size: Optional[List[int]],
) -> Tuple[str, Optional[List[int]], bool]:
    """裁切 data-uri 图像到前台窗口 ROI。返回 (image_b64, offset_xy, cropped)。"""
    if not ASSIST_ROI_VISION_FALLBACK or not foreground_rect or len(foreground_rect) < 4:
        return image_b64, None, False
    if not capture_size or len(capture_size) < 2:
        return image_b64, None, False
    try:
        from PIL import Image

        raw = image_b64
        if "," in raw:
            raw = raw.split(",", 1)[1]
        data = base64.b64decode(raw)
        img = Image.open(io.BytesIO(data)).convert("RGB")
        cap_w, cap_h = int(capture_size[0]), int(capture_size[1])
        if img.size != (cap_w, cap_h):
            scale_x = img.size[0] / cap_w
            scale_y = img.size[1] / cap_h
        else:
            scale_x = scale_y = 1.0
        x1, y1, x2, y2 = [int(v) for v in foreground_rect[:4]]
        px1 = max(0, int(x1 * scale_x))
        py1 = max(0, int(y1 * scale_y))
        px2 = min(img.size[0], int(x2 * scale_x))
        py2 = min(img.size[1], int(y2 * scale_y))
        if px2 - px1 < 80 or py2 - py1 < 80:
            return image_b64, None, False
        cropped = img.crop((px1, py1, px2, py2))
        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=92)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}", [px1, py1], True
    except Exception:
        return image_b64, None, False
