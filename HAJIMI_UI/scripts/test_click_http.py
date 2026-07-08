# -*- coding: utf-8 -*-
"""固定坐标点击冒烟 — 经 8011 Sidecar POST /api/demo/debug/click 调用 clicker。"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import DEMO_KEY, L5_API_URL as _CONFIG_L5_URL  # noqa: E402


def _get_base(override: str = "") -> str:
    return (override or _CONFIG_L5_URL).rstrip("/")


def _get(path: str, base: str, timeout: float = 5.0) -> tuple[int, dict | str]:
    req = urllib.request.Request(f"{base}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except Exception as exc:
        return 0, str(exc)


def _post(path: str, payload: dict, base: str, *, timeout: float = 30.0) -> tuple[int, dict | str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Demo-Key": DEMO_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def main() -> int:
    parser = argparse.ArgumentParser(description="HTTP 固定坐标 click 冒烟（8011 /debug/click）")
    parser.add_argument("--base-url", default="", help="覆盖 L5_API_URL")
    parser.add_argument("--x", type=int, default=960)
    parser.add_argument("--y", type=int, default=540)
    parser.add_argument("--clicks", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--button", default="left", choices=("left", "right", "middle"))
    parser.add_argument(
        "--require-sidecar",
        action="store_true",
        help="Sidecar 不可达时返回非零",
    )
    args = parser.parse_args()

    base = _get_base(args.base_url)
    print("=== test_click_http ===")
    print(f"L5 Sidecar: {base}")
    print(f"Target: ({args.x}, {args.y}) button={args.button} clicks={args.clicks}")

    code, health = _get("/api/demo/health/live", base)
    if code == 404:
        code, health = _get("/api/demo/health", base)
    if code not in (200, 503):
        msg = f"L5 Sidecar not reachable (HTTP {code}): {health}"
        print(f"FAIL: {msg}")
        print("Hint: run scripts\\start_l5_sidecar.bat first")
        return 1 if args.require_sidecar else 1

    code, body = _post(
        "/api/demo/debug/click",
        {"x": args.x, "y": args.y, "clicks": args.clicks, "button": args.button},
        base,
    )
    if code != 200:
        print(f"FAIL: /debug/click HTTP {code}: {body}")
        if code == 404:
            print("Hint: restart 8011 Sidecar to load the new /debug/click route")
        return 1

    if not isinstance(body, dict) or not body.get("success"):
        print(f"FAIL: unexpected response: {body}")
        return 1

    print(json.dumps(body, ensure_ascii=False))
    print("PASS: HTTP click dispatched — check mouse moved on screen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
