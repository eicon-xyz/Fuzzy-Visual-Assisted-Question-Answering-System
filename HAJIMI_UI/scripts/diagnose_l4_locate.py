"""
L4 Locator 定位诊断 — 捕获真实屏幕并调用 Vision 定位。

用法:
  python scripts/diagnose_l4_locate.py
  python scripts/diagnose_l4_locate.py --step "点击开始菜单"
  python scripts/diagnose_l4_locate.py --json

退出码: 0=解析到 [POINT], 1=失败或未配置 LLM
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _capture_and_encode():
    from core.screen_utils import (
        capture_screen,
        downscale_for_api,
        get_screen_metrics,
        get_upload_jpeg_quality,
        get_upload_max_side,
        pil_to_data_uri,
    )

    screenshot = capture_screen()
    if screenshot is None:
        raise RuntimeError("屏幕捕获失败")

    sw, sh = screenshot.size
    upload = downscale_for_api(screenshot, get_upload_max_side())
    uri = pil_to_data_uri(upload, quality=get_upload_jpeg_quality())
    return uri, [sw, sh], [upload.size[0], upload.size[1]], get_screen_metrics()


def run_diagnose(step_desc: str) -> dict:
    from server.services.l4.locator import locate_l4_step
    from server.services.l4.point_parser import parse_point_tag
    from server.services.l4.types import L4ScreenContext

    image_uri, capture_size, upload_size, metrics = _capture_and_encode()
    step = {
        "action": "click",
        "description": step_desc,
        "target": step_desc,
    }
    ctx = L4ScreenContext(
        capture_size=capture_size,
        upload_size=upload_size,
        screen_metrics=metrics,
    )

    t0 = time.perf_counter()
    result = locate_l4_step(step, image_b64=image_uri, screen_ctx=ctx)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    raw = (result.llm_meta or {}).get("raw_locator_output", "")
    _, coord, label = parse_point_tag(raw)

    return {
        "step": step_desc,
        "capture_size": capture_size,
        "upload_size": upload_size,
        "latency_ms": elapsed_ms,
        "raw_locator_output": raw,
        "has_point": coord is not None,
        "coord": coord,
        "label": label,
        "has_annotation": result.annotation is not None,
        "highlight_bbox": (
            result.annotation.highlight_bbox if result.annotation else None
        ),
        "llm_meta": result.llm_meta,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="L4 Locator 真实屏幕定位诊断")
    parser.add_argument(
        "--step",
        default="点击任务栏上的开始按钮",
        help="模拟定位的步骤描述",
    )
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    try:
        from core.user_settings import apply_user_settings

        apply_user_settings()
        report = run_diagnose(args.step)
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[FAIL] {exc}")
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=== L4 Locator 诊断 ===")
        print(f"步骤: {report['step']}")
        print(f"捕获: {report['capture_size']} → 上传: {report['upload_size']}")
        print(f"耗时: {report['latency_ms']} ms")
        print(f"raw_locator_output: {report['raw_locator_output'][:200]!r}")
        if report["has_point"]:
            print(f"[OK] [POINT] coord={report['coord']} label={report['label']!r}")
            if report["highlight_bbox"]:
                print(f"     highlight_bbox={report['highlight_bbox']}")
        else:
            print("[FAIL] 未解析到有效 [POINT:x,y]")

    return 0 if report.get("has_point") else 1


if __name__ == "__main__":
    sys.exit(main())
