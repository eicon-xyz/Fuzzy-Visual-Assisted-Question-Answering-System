#!/usr/bin/env python3
"""
HAJIMI Demo 前端快速联调脚本
用途：帮助前端开发者（B）验证后端 API 是否正常工作
运行前请确保：
  1. 后端服务已启动：
     cd D:\模糊视觉辅助问答系统
     python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
     # 或：cd server && python main.py
  2. 已安装 httpx：pip install httpx
"""
import json
import sys
import httpx

# Windows 控制台中文显示优化
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ────────────────────────── 配置 ──────────────────────────
BASE_URL = "http://localhost:8000"
DEMO_KEY = "hajimi-demo-2026"
TIMEOUT = 60.0

HEADERS = {
    "X-Demo-Key": DEMO_KEY,
    "Content-Type": "application/json",
}
CLIENT = httpx.Client(timeout=TIMEOUT)


def print_json(title, data):
    """美观打印 JSON"""
    print(f"\n{'=' * 20} {title} {'=' * 20}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def test_health():
    """测试服务是否活着"""
    r = CLIENT.get(f"{BASE_URL}/api/demo/health")
    print_json("健康检查", r.json())
    assert r.status_code == 200, f"健康检查失败: {r.status_code}"


def test_process(query="怎么安装微信？"):
    """
    测试核心流程
    这是前端最重要的接口：输入用户问题，拿到步骤 + 标注坐标
    """
    r = CLIENT.post(
        f"{BASE_URL}/api/demo/process",
        headers=HEADERS,
        json={
            "query": query,
            "window_title": "桌面",
            "context": [],
        },
    )
    data = r.json()
    print_json("核心流程 /api/demo/process", data)
    assert r.status_code == 200, f"process 失败: {r.status_code}"
    assert data["success"] is True
    assert len(data["steps"]) > 0, "没有返回步骤"
    return data["task_id"], data["steps"], data["ui_elements"]


def test_step(task_id):
    """测试推进蓝图"""
    r = CLIENT.post(
        f"{BASE_URL}/api/demo/step",
        headers=HEADERS,
        json={
            "task_id": task_id,
            "action": "advance",
            "step_index": 1,
            "fingerprint": "mock-fingerprint-for-demo",
        },
    )
    data = r.json()
    print_json("推进步骤 /api/demo/step", data)
    assert r.status_code == 200
    return data


def test_report(task_id):
    """测试审计上报"""
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
    data = r.json()
    print_json("审计上报 /api/demo/report", data)
    assert r.status_code == 200


def show_frontend_hints(steps, ui_elements):
    """
    打印前端开发提示：
    告诉 B 哪些字段是用来画 UI 的
    """
    print(f"\n{'=' * 20} 前端开发提示 {'=' * 20}")
    print(f"共返回 {len(steps)} 个步骤，{len(ui_elements)} 个 UI 元素")
    print("\n当前应高亮执行的步骤:")
    for step in steps:
        if step["status"] == "active":
            ann = step.get("annotation") or {}
            print(f"  步骤 {step['step_index']}: {step['action']}")
            print(f"  说明: {step['description']}")
            print(f"  目标元素 ID: {step['target_element_id']}")
            print(f"  标注类型: {ann.get('type')}")
            print(f"  高亮框: {ann.get('highlight_bbox')}")
            print(f"  箭头: {ann.get('arrow_from')} -> {ann.get('arrow_to')}")
            print(f"  标签位置: {ann.get('label_position')}, 文字: {ann.get('label_text')}")


if __name__ == "__main__":
    try:
        print("开始测试 HAJIMI Demo 后端...")
        print(f"目标地址: {BASE_URL}")

        test_health()
        task_id, steps, ui_elements = test_process()
        test_step(task_id)
        test_report(task_id)
        show_frontend_hints(steps, ui_elements)

        print("\n[OK] 后端联调测试全部通过！")
        print(f"\n你可以打开浏览器查看 API 文档: {BASE_URL}/docs")

    except CLIENT.ConnectError:
        print(f"\n[错误] 无法连接到后端: {BASE_URL}")
        print("请确认后端已启动: cd server && python main.py")
        sys.exit(1)

    except AssertionError as e:
        print(f"\n[错误] 测试断言失败: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"\n[错误] 测试异常: {type(e).__name__}: {e}")
        sys.exit(1)
