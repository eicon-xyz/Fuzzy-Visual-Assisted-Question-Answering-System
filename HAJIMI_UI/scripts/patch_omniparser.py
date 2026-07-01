"""Patch E:\\Tools\\OmniParser util/utils.py — fix empty-screen 500 on /parse/."""
from __future__ import annotations

import os
import sys
from pathlib import Path

MARKER = "# HAJIMI_PATCH_EMPTY_SOM"


def patch_utils(utils_path: Path) -> bool:
    text = utils_path.read_text(encoding="utf-8")
    if MARKER in text:
        return False

    old_int = """def int_box_area(box, w, h):
    x1, y1, x2, y2 = box
    int_box = [int(x1*w), int(y1*h), int(x2*w), int(y2*h)]
    area = (int_box[2] - int_box[0]) * (int_box[3] - int_box[1])
    return area"""

    new_int = f"""def int_box_area(box, w, h):
    {MARKER}
    if not box or len(box) < 4:
        return 0
    try:
        x1, y1, x2, y2 = box
    except (TypeError, ValueError):
        return 0
    int_box = [int(x1*w), int(y1*h), int(x2*w), int(y2*h)]
    area = (int_box[2] - int_box[0]) * (int_box[3] - int_box[1])
    return area"""

    if old_int not in text:
        print(f"[patch] int_box_area block not found in {utils_path}", file=sys.stderr)
        return False
    text = text.replace(old_int, new_int, 1)

    anchor = "    filtered_boxes = remove_overlap_new(boxes=xyxy_elem, iou_threshold=iou_threshold, ocr_bbox=ocr_bbox_elem)\n"
    insert = anchor + (
        f"\n"
        f"    if not filtered_boxes:\n"
        f"        {MARKER}_return\n"
        f"        pil_img = Image.fromarray(image_source)\n"
        f"        buffered = io.BytesIO()\n"
        f"        pil_img.save(buffered, format=\"PNG\")\n"
        f"        encoded_image = base64.b64encode(buffered.getvalue()).decode(\"ascii\")\n"
        f"        return encoded_image, {{}}, []\n"
    )
    if anchor not in text:
        print(f"[patch] get_som_labeled_img anchor not found in {utils_path}", file=sys.stderr)
        return False
    text = text.replace(anchor, insert, 1)

    utils_path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    omni_root = Path(os.environ.get("OMNI_ROOT", r"E:\Tools\OmniParser"))
    utils_path = omni_root / "util" / "utils.py"
    if not utils_path.is_file():
        print(f"[patch] not found: {utils_path}", file=sys.stderr)
        return 1
    if patch_utils(utils_path):
        print(f"[patch] applied to {utils_path}")
    else:
        print(f"[patch] already patched or skipped: {utils_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
