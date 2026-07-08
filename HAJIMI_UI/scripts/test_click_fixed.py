# -*- coding: utf-8 -*-
"""固定坐标点击冒烟 — 直接调用 L5 Sidecar 的 clicker.click_at（无需 HTTP / Omni / LLM）。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _resolve_l5_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from core.paths import resolve_l5_root

    return resolve_l5_root()


def main() -> int:
    parser = argparse.ArgumentParser(description="固定坐标 clicker 冒烟（直接调 pyautogui）")
    parser.add_argument("--x", type=int, default=960, help="目标 X（默认屏幕中心 960）")
    parser.add_argument("--y", type=int, default=540, help="目标 Y（默认屏幕中心 540）")
    parser.add_argument("--clicks", type=int, default=1, choices=(1, 2, 3), help="点击次数")
    parser.add_argument(
        "--button",
        default="left",
        choices=("left", "right", "middle"),
        help="鼠标按键",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="点击前等待秒数（便于切到桌面）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印坐标，不移动鼠标",
    )
    args = parser.parse_args()

    l5_root = _resolve_l5_root()
    if not (l5_root / "server" / "services" / "executor" / "clicker.py").is_file():
        print(f"ERROR: L5 Sidecar not found at {l5_root}")
        print("Set HAJIMI_L5_ROOT to server_A if using a custom path.")
        return 1

    sys.path.insert(0, str(l5_root))
    from server.services.executor.clicker import click_at  # noqa: E402

    print("=== test_click_fixed ===")
    print(f"L5 root: {l5_root}")
    print(f"Target: ({args.x}, {args.y}) button={args.button} clicks={args.clicks}")

    if args.dry_run:
        print(json.dumps({"success": True, "dry_run": True, "x": args.x, "y": args.y}))
        return 0

    if args.delay > 0:
        print(f"Clicking in {args.delay:.0f}s — switch to desktop now...")
        time.sleep(args.delay)

    result = click_at([args.x, args.y], button=args.button, clicks=args.clicks)
    print(json.dumps(result, ensure_ascii=False))

    if not result.get("success"):
        return 1
    print("PASS: mouse click dispatched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
