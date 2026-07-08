"""
HAJIMI Demo API 测试脚本
供前端开发者快速验证后端接口是否正常工作
"""

import json
import sys

import httpx

# Windows 控制台中文显示优化
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_URL = "http://localhost:8010"
HEADERS = {
    "X-Demo-Key": "hajimi-demo-2026",
    "Content-Type": "application/json",
}
CLIENT = httpx.Client(timeout=60.0)


def print_json(title, data):
    print(f"\n=== {title} ===")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def test_health():
    r = CLIENT.get(f"{BASE_URL}/api/demo/health")
    print_json("健康检查", r.json())
    assert r.status_code == 200


def test_process(query: str = "怎么安装微信？"):
    r = CLIENT.post(
        f"{BASE_URL}/api/demo/process",
        headers=HEADERS,
        json={"query": query, "window_title": "桌面"},
    )
    data = r.json()
    print_json("核心流程", data)
    assert r.status_code == 200
    assert data["success"] is True
    return data["task_id"], data["steps"]


def test_step(task_id: str):
    r = CLIENT.post(
        f"{BASE_URL}/api/demo/step",
        headers=HEADERS,
        json={
            "task_id": task_id,
            "action": "advance",
            "step_index": 1,
            "fingerprint": "mock-fingerprint",
        },
    )
    print_json("推进步骤", r.json())
    assert r.status_code == 200


def test_report(task_id: str):
    r = CLIENT.post(
        f"{BASE_URL}/api/demo/report",
        headers=HEADERS,
        json={
            "task_id": task_id,
            "result": "success",
            "feedback_type": "useful",
            "duration_ms": 5200,
        },
    )
    print_json("审计上报", r.json())
    assert r.status_code == 200


if __name__ == "__main__":
    print("开始测试 HAJIMI Demo API...")
    test_health()
    task_id, steps = test_process()
    test_step(task_id)
    test_report(task_id)
    print("\n[OK] 所有测试通过")
