"""
Icon Stitch — Crop + Zoom + Stitch for precise icon identification

Takes OmniParser bbox regions from the screenshot, enlarges each to 128x128,
stitches them into one strip with element_id labels, sends to LLM in one call.
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Sizes
ICON_SIZE = 200  # target crop size (square)
MAX_PER_STRIP = 4  # max icons per strip image
LABEL_HEIGHT = 24  # pixels for label below each icon
PADDING = 4  # pixels between icons


def _crop_and_resize(image: Image.Image, bbox: List[float]) -> Image.Image:
    """Crop a bbox region from image and resize to ICON_SIZE×ICON_SIZE."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    # Add 20% padding around bbox for context
    w, h = x2 - x1, y2 - y1
    pad_w, pad_h = int(w * 0.2), int(h * 0.2)
    x1 = max(0, x1 - pad_w)
    y1 = max(0, y1 - pad_h)
    x2 = min(image.width, x2 + pad_w)
    y2 = min(image.height, y2 + pad_h)

    if x2 <= x1 or y2 <= y1:
        return Image.new("RGB", (ICON_SIZE, ICON_SIZE), "black")

    crop = image.crop((x1, y1, x2, y2))
    return crop.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)


def _get_font(size: int = 14) -> ImageFont.ImageFont:
    """Get a usable font."""
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
        except Exception:
            return ImageFont.load_default()


def build_icon_strips(
    image: Image.Image,
    elements: List[dict],
) -> List[str]:
    """
    Build stitched icon strip images, returning base64 JPEG data URIs.

    Args:
        image: Full screenshot PIL Image (RGB)
        elements: List of element dicts with 'bbox', 'element_id', 'text'

    Returns:
        List of base64 JPEG data URI strings (one per strip of ≤MAX_PER_STRIP icons)
    """
    strips: List[str] = []
    batch: List[Tuple[str, Image.Image]] = []

    for el in elements:
        bbox = el.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        eid = el.get("element_id", "?")
        icon = _crop_and_resize(image, bbox)
        batch.append((eid, icon))

        if len(batch) >= MAX_PER_STRIP:
            strips.append(_stitch_batch(batch))
            batch = []

    if batch:
        strips.append(_stitch_batch(batch))

    return strips


def build_icon_strips_from_client_elements(
    image: Image.Image,
    elements: list,
) -> List[str]:
    """
    Build strips from server.models.schemas.UIElement objects.
    """
    el_dicts = [
        {
            "bbox": [el.bbox[0], el.bbox[1], el.bbox[2], el.bbox[3]],
            "element_id": el.element_id,
            "text": el.text or "",
        }
        for el in elements
    ]
    return build_icon_strips(image, el_dicts)


def _stitch_batch(batch: List[Tuple[str, Image.Image]]) -> str:
    """Stitch a batch of icon images into one strip with labels. Returns base64 JPEG URI."""
    n = len(batch)
    strip_w = n * ICON_SIZE + (n + 1) * PADDING
    strip_h = ICON_SIZE + LABEL_HEIGHT + PADDING * 2

    strip = Image.new("RGB", (strip_w, strip_h), (30, 30, 30))
    draw = ImageDraw.Draw(strip)
    font = _get_font(13)

    for i, (eid, icon) in enumerate(batch):
        x = PADDING + i * (ICON_SIZE + PADDING)
        y = PADDING
        strip.paste(icon, (x, y))

        # Label below icon
        label = str(eid)
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        lx = x + (ICON_SIZE - tw) // 2
        ly = y + ICON_SIZE + 4
        draw.text((lx, ly), label, fill=(255, 255, 255), font=font)

    buf = BytesIO()
    strip.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def identify_from_strips(
    strips: List[str],
    target_name: str,
) -> Optional[str]:
    """
    Send stitched icon strips to LLM for identification.

    Args:
        strips: List of base64 JPEG data URIs from build_icon_strips()
        target_name: e.g. "NetEase Cloud Music"

    Returns:
        element_id string like "~43", or None if not found
    """
    import json
    import re

    from server.services.llm.providers import call_llm

    images = [{"base64Jpeg": s, "label": f"icons_{i}"} for i, s in enumerate(strips)]

    system_prompt = (
        "You are an icon identifier. You see enlarged desktop icons with element IDs "
        "below each icon. Read the text on each icon carefully. "
        "Find the specified target app icon. "
        'Output ONLY: {"element_id": "~N"}. No thinking. No explanation.'
    )

    user_text = (
        f"These are enlarged desktop icons. Each has its element ID below it. "
        f"Look at the icon image and any readable text on it. "
        f"Find the icon for: {target_name}. "
        f"Return ONLY the element_id as JSON."
    )

    raw = call_llm(
        user_text=user_text,
        images=images,
        system_prompt=system_prompt,
        temperature=0.0,
        max_tokens=32,
        timeout=30,
    )

    # Extract element_id from response
    m = re.search(r"~[\d]+", raw)
    if m:
        return m.group()

    # Try JSON parse
    try:
        data = json.loads(raw.strip())
        return data.get("element_id")
    except Exception:
        pass

    return None
