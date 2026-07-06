"""
HAJIMI Server 测试共享 fixtures
供多 Agent 并行开发期间回归测试使用
"""

from typing import List

import pytest

from server.models.schemas import UIElement


@pytest.fixture
def mock_elements() -> List[UIElement]:
    """标准 UI 元素 fixtures，所有测试共用"""
    return [
        UIElement(
            element_id="~1",
            bbox=[0, 0, 100, 40],
            element_type="button",
            text="下载",
            confidence=0.95,
            center=[50, 20],
        ),
        UIElement(
            element_id="~2",
            bbox=[200, 0, 300, 40],
            element_type="input",
            text="搜索",
            confidence=0.90,
            center=[250, 20],
        ),
        UIElement(
            element_id="~3",
            bbox=[0, 60, 100, 100],
            element_type="icon",
            text="Edge",
            confidence=0.88,
            center=[50, 80],
        ),
    ]


@pytest.fixture
def mock_llm_steps() -> List[dict]:
    """标准 LLM 返回步骤，含 target_element_id"""
    return [
        {
            "action": "点击下载",
            "description": "点击下载按钮",
            "target_element_id": "~1",
        },
        {
            "action": "输入地址",
            "description": "在地址栏输入网址",
            "target_element_id": "~2",
        },
        {
            "action": "等待完成",
            "description": "等待下载完成",
            "target_element_id": "",
        },
    ]


@pytest.fixture
def mock_scenario_elements() -> dict:
    """与 llm_ai.py 中 SCENARIO_ELEMENTS 一致的 mock 元素"""
    return {
        "wechat": [
            UIElement(
                element_id="~1",
                bbox=[120, 340, 240, 380],
                element_type="icon",
                text="Microsoft Edge",
                confidence=0.95,
                center=[180, 360],
            ),
            UIElement(
                element_id="~2",
                bbox=[860, 620, 1020, 660],
                element_type="button",
                text="下载",
                confidence=0.91,
                center=[940, 640],
            ),
            UIElement(
                element_id="~3",
                bbox=[540, 420, 740, 460],
                element_type="input",
                text="",
                confidence=0.88,
                center=[640, 440],
            ),
        ],
        "screenshot": [
            UIElement(
                element_id="~1",
                bbox=[20, 20, 60, 60],
                element_type="icon",
                text="截图工具",
                confidence=0.94,
                center=[40, 40],
            ),
            UIElement(
                element_id="~2",
                bbox=[300, 300, 500, 400],
                element_type="button",
                text="新建截图",
                confidence=0.92,
                center=[400, 350],
            ),
        ],
        "default": [
            UIElement(
                element_id="~1",
                bbox=[100, 100, 200, 140],
                element_type="button",
                text="开始",
                confidence=0.90,
                center=[150, 120],
            ),
            UIElement(
                element_id="~2",
                bbox=[300, 300, 420, 340],
                element_type="button",
                text="设置",
                confidence=0.88,
                center=[360, 320],
            ),
        ],
    }
