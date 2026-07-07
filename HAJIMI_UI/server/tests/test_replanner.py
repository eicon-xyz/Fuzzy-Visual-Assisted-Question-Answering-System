"""
P2「动态重规划」单元与接口测试（5 条核心用例）

运行方式：
    python -m pytest server/tests/test_replanner.py -v
"""
from typing import List

import pytest
from fastapi.testclient import TestClient

from server.config import settings
from server.main import app
from server.models.schemas import Blueprint, Intent, Step, UIElement
from server.services.planning.replanner import replan_steps
from server.storage.memory import TaskState, task_store


client = TestClient(app)


@pytest.fixture(autouse=True)
def _cleanup_task_store():
    """每个用例结束后清理任务存储"""
    yield
    task_store.delete("test-task")


def _make_state(
    steps: List[Step],
    current_step: int = 1,
    state: str = "executing",
    query: str = "安装微信",
    task_id: str = "test-task",
) -> TaskState:
    """构造并写入一个任务状态，供 /step 接口测试使用"""
    task_state = TaskState(
        task_id=task_id,
        query=query,
        intent=Intent(
            category="operation_guide",
            summary=query,
            reference_type="explicit",
            confidence=0.92,
            needs_clarification=False,
        ),
        blueprint=Blueprint(
            name=query,
            total_steps=len(steps),
            current_step=current_step,
            state=state,
        ),
        steps=steps,
        ui_elements=[],
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        fingerprint=None,
    )
    task_store.update(task_state)
    return task_state


def _address_bar_element() -> UIElement:
    return UIElement(
        element_id="~1",
        bbox=[540, 60, 1200, 100],
        element_type="input",
        text="",
        confidence=0.90,
        center=[870, 80],
    )


def _download_button_element() -> UIElement:
    return UIElement(
        element_id="~1",
        bbox=[860, 620, 1020, 660],
        element_type="button",
        text="下载",
        confidence=0.91,
        center=[940, 640],
    )


def test_advance_triggers_replanning_binds_address_bar(monkeypatch):
    """1. 浏览器打开后重规划：Step 2 无绑定 + 新截图含地址栏 input → target 指向地址栏"""
    steps = [
        Step(
            step_index=1,
            action="打开浏览器",
            description="双击桌面上的 Microsoft Edge 图标",
            target_element_id="~1",
            status="active",
            annotation=None,
        ),
        Step(
            step_index=2,
            action="访问微信官网",
            description="在浏览器地址栏输入 weixin.qq.com 并回车",
            target_element_id=None,
            status="pending",
            annotation=None,
        ),
        Step(
            step_index=3,
            action="点击下载",
            description="在官网首页找到下载按钮并点击",
            target_element_id=None,
            status="pending",
            annotation=None,
        ),
    ]
    _make_state(steps, current_step=1, state="executing")

    address_bar = _address_bar_element()

    def _mock_parse_screenshot(image_base64: str):
        return [address_bar]

    def _mock_call_replan_llm(prompt: str):
        return {
            "steps": [
                {
                    "step_index": 2,
                    "action": "访问微信官网",
                    "description": "在浏览器地址栏输入 weixin.qq.com 并回车",
                    "target_element_id": "~1",
                }
            ]
        }

    monkeypatch.setattr("server.routes.demo.parse_screenshot", _mock_parse_screenshot)
    monkeypatch.setattr(
        "server.services.planning.replanner._call_replan_llm", _mock_call_replan_llm
    )

    response = client.post(
        "/api/demo/step",
        headers={"X-Demo-Key": settings.DEMO_KEY},
        json={
            "task_id": "test-task",
            "action": "advance",
            "step_index": 1,
            "image": "fake-base64-screenshot",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "advance"
    assert data["current_step"] == 2
    next_step = data["next_step"]
    assert next_step["target_element_id"] == "~1"
    assert next_step["annotation"] is not None
    assert next_step["annotation"]["highlight_bbox"] == address_bar.bbox


def test_replan_binds_download_button(monkeypatch):
    """2. 进入官网后重规划：Step 3 无绑定 + 新截图含下载 button → target 指向下载按钮"""
    steps = [
        Step(
            step_index=1,
            action="打开浏览器",
            description="双击桌面上的 Microsoft Edge 图标",
            target_element_id="~1",
            status="done",
            annotation=None,
        ),
        Step(
            step_index=2,
            action="访问微信官网",
            description="在浏览器地址栏输入 weixin.qq.com 并回车",
            target_element_id="~2",
            status="done",
            annotation=None,
        ),
        Step(
            step_index=3,
            action="点击下载",
            description="在官网首页找到下载按钮并点击",
            target_element_id=None,
            status="active",
            annotation=None,
        ),
    ]
    download_button = _download_button_element()

    def _mock_call_replan_llm(prompt: str):
        return {
            "steps": [
                {
                    "step_index": 3,
                    "action": "点击下载",
                    "description": "在官网首页找到下载按钮并点击",
                    "target_element_id": "~1",
                }
            ]
        }

    monkeypatch.setattr(
        "server.services.planning.replanner._call_replan_llm", _mock_call_replan_llm
    )

    updated = replan_steps("安装微信", 2, steps, [download_button])

    assert updated[2].target_element_id == "~1"
    assert updated[2].annotation is not None
    assert updated[2].annotation.highlight_bbox == download_button.bbox
    # 已绑定步骤保持不变
    assert updated[0].target_element_id == "~1"
    assert updated[1].target_element_id == "~2"


def test_replan_keeps_empty_when_no_match(monkeypatch):
    """3. 仍无匹配元素：新截图仍未出现目标 → 保持空，纯文字指引"""
    steps = [
        Step(
            step_index=1,
            action="打开浏览器",
            description="双击桌面上的 Microsoft Edge 图标",
            target_element_id="~1",
            status="done",
            annotation=None,
        ),
        Step(
            step_index=2,
            action="访问微信官网",
            description="在浏览器地址栏输入 weixin.qq.com 并回车",
            target_element_id=None,
            status="active",
            annotation=None,
        ),
    ]
    new_elements = [
        UIElement(
            element_id="~1",
            bbox=[1200, 20, 1240, 60],
            element_type="button",
            text="关闭",
            confidence=0.90,
            center=[1220, 40],
        )
    ]

    def _mock_call_replan_llm(prompt: str):
        return {
            "steps": [
                {
                    "step_index": 2,
                    "action": "访问微信官网",
                    "description": "在浏览器地址栏输入 weixin.qq.com 并回车",
                    "target_element_id": "",
                }
            ]
        }

    monkeypatch.setattr(
        "server.services.planning.replanner._call_replan_llm", _mock_call_replan_llm
    )

    updated = replan_steps("安装微信", 1, steps, new_elements)

    assert updated[1].target_element_id is None
    assert updated[1].annotation is None


def test_rollback_does_not_trigger_replanning(monkeypatch):
    """4. 用户回退：action='rollback' 不触发重规划"""
    steps = [
        Step(
            step_index=1,
            action="打开浏览器",
            description="双击桌面上的 Microsoft Edge 图标",
            target_element_id="~1",
            status="done",
            annotation=None,
        ),
        Step(
            step_index=2,
            action="访问微信官网",
            description="在浏览器地址栏输入 weixin.qq.com 并回车",
            target_element_id=None,
            status="active",
            annotation=None,
        ),
    ]
    _make_state(steps, current_step=2, state="executing")

    call_count = 0

    def _mock_parse_screenshot(image_base64: str):
        return [_address_bar_element()]

    def _mock_call_replan_llm(prompt: str):
        nonlocal call_count
        call_count += 1
        return {"steps": []}

    monkeypatch.setattr("server.routes.demo.parse_screenshot", _mock_parse_screenshot)
    monkeypatch.setattr(
        "server.services.planning.replanner._call_replan_llm", _mock_call_replan_llm
    )

    response = client.post(
        "/api/demo/step",
        headers={"X-Demo-Key": settings.DEMO_KEY},
        json={
            "task_id": "test-task",
            "action": "rollback",
            "step_index": 2,
            "image": "fake-base64-screenshot",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "rollback"
    assert call_count == 0


def test_replan_llm_error_returns_original_steps(monkeypatch):
    """5. 网络异常：LLM 调用失败 → 返回原步骤，不崩溃"""
    steps = [
        Step(
            step_index=1,
            action="打开浏览器",
            description="双击桌面上的 Microsoft Edge 图标",
            target_element_id="~1",
            status="done",
            annotation=None,
        ),
        Step(
            step_index=2,
            action="访问微信官网",
            description="在浏览器地址栏输入 weixin.qq.com 并回车",
            target_element_id=None,
            status="active",
            annotation=None,
        ),
    ]
    new_elements = [_address_bar_element()]

    class _FailingClient:
        def __init__(self, timeout: int = 30):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            raise RuntimeError("network timeout")

    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-key")
    monkeypatch.setattr(
        "server.services.planning.replanner.httpx.Client", _FailingClient
    )

    updated = replan_steps("安装微信", 1, steps, new_elements)

    assert len(updated) == 2
    assert updated[1].target_element_id is None
    assert updated[1].annotation is None
