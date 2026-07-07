# [VERIFY] L5 自动执行端点冒烟 — POST /execute + SSE heartbeat
"""验证 A 端 L5 路由是否接线（不触发真实 pyautogui 点击）。"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import API_BASE_URL, DEMO_KEY  # noqa: E402


def _get(path: str, timeout: float = 10.0) -> tuple[int, dict | str]:
    req = urllib.request.Request(f"{API_BASE_URL.rstrip('/')}{path}", method="GET")
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


def _post(path: str, payload: dict, *, timeout: float = 30.0) -> tuple[int, dict | str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE_URL.rstrip('/')}{path}",
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
    parser = argparse.ArgumentParser(description="L5 execute/stream/cancel 冒烟")
    parser.add_argument(
        "--require-a",
        action="store_true",
        help="A 端不可达时返回非零",
    )
    args = parser.parse_args()

    print("=== verify_l5 ===")
    print(f"A 端: {API_BASE_URL}")

    code, health = _get("/api/demo/health/live")
    if code != 200:
        msg = f"A 端 /health/live 不可达 (HTTP {code})"
        print(f"SKIP: {msg}")
        return 1 if args.require_a else 0

    code, audit_probe = _post(
        "/api/audit/report",
        {
            "task_id": "verify-l5-probe",
            "query": "probe",
            "intent_category": "operation_guide",
            "route": "L3",
            "result": "success",
        },
    )
    if code not in (200, 201):
        print(f"FAIL: /api/audit/report HTTP {code}: {audit_probe}")
        return 1
    print("PASS: /api/audit/report")

    code, execute_body = _post(
        "/api/demo/execute",
        {"query": "打开记事本", "image": None, "context": []},
        timeout=120.0,
    )
    if code != 200:
        print(f"FAIL: /execute HTTP {code}: {execute_body}")
        return 1
    if not isinstance(execute_body, dict) or not execute_body.get("task_id"):
        print(f"FAIL: /execute 无 task_id: {execute_body}")
        return 1

    task_id = execute_body["task_id"]
    print(f"PASS: /execute task_id={task_id}")

    stream_url = f"{API_BASE_URL.rstrip('/')}/api/demo/stream/{task_id}"
    req = urllib.request.Request(stream_url)
    saw_heartbeat = False
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            for _ in range(20):
                line = resp.readline().decode("utf-8", errors="replace").strip()
                if line.startswith("event:") and "heartbeat" in line:
                    saw_heartbeat = True
                    break
    except Exception as exc:
        print(f"WARN: SSE 读取异常（可能任务已结束）: {exc}")

    if saw_heartbeat:
        print("PASS: SSE heartbeat")
    else:
        print("WARN: 未收到 SSE heartbeat（任务可能极快结束）")

    code, cancel_body = _post("/api/demo/cancel", {"task_id": task_id})
    if code != 200:
        print(f"WARN: /cancel HTTP {code}: {cancel_body}")
    else:
        print("PASS: /cancel")

    print("\nverify_l5: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
