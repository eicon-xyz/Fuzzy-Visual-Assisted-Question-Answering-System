"""
P0「LLM 元素感知」单元测试（6 条核心用例）

运行方式：
    python -m pytest server/tests/test_perception.py -v
"""
from typing import List, Optional

import pytest

from server.config import settings
from server.models.schemas import UIElement
from server.services.planning import generate_steps, process_query


@pytest.fixture(autouse=True)
def _disable_real_llm(monkeypatch):
    """关闭真实 LLM，确保使用 mock fallback"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", False)
    monkeypatch.setattr("server.services.llm.client.reload_settings", lambda: None)


def _make_elements() -> List[UIElement]:
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
            element_type="input",
            text="密码",
            confidence=0.88,
            center=[50, 80],
        ),
    ]


def test_semantic_match_download_button(monkeypatch):
    """1. 语义匹配：LLM 指向下载按钮 → 生成高亮标注"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", True)
    elements = _make_elements()
    monkeypatch.setattr(
        "server.services.planning.router.SCENARIO_ELEMENTS",
        {"wechat": elements, "screenshot": [], "default": []},
    )
    captured: List[Optional[List[UIElement]]] = []

    def _mock_call(query: str, elements: Optional[List[UIElement]] = None, timeout: int = 30, **kwargs):
        captured.append(elements)
        return {
            "steps": [
                {"action": "点击下载", "description": "点击下载按钮", "target_element_id": "~1"},
            ]
        }, None, 10, "primary", False

    monkeypatch.setattr("server.services.planning.router.call_deepseek", _mock_call)

    response = process_query("点击下载按钮")
    step = response.steps[0]
    assert step.target_element_id == "~1"
    assert step.annotation is not None
    assert step.annotation.highlight_bbox == elements[0].bbox
    # 验证元素列表确实传入了 LLM
    assert captured and captured[0] is not None
    assert captured[0][0].element_id == "~1"


def test_type_text_match_password_input(monkeypatch):
    """2. 类型-文本匹配：输入密码 → 绑定密码输入框"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", True)
    elements = _make_elements()
    monkeypatch.setattr(
        "server.services.planning.router.SCENARIO_ELEMENTS",
        {"wechat": [], "screenshot": [], "default": elements},
    )

    def _mock_call(query: str, elements: Optional[List[UIElement]] = None, timeout: int = 30, **kwargs):
        return {
            "steps": [
                {"action": "输入密码", "description": "在密码框输入密码", "target_element_id": "~3"},
            ]
        }, None, 10, "primary", False

    monkeypatch.setattr("server.services.planning.router.call_deepseek", _mock_call)

    response = process_query("输入密码")
    step = response.steps[0]
    assert step.target_element_id == "~3"
    assert step.annotation is not None
    assert step.annotation.label_text == "~3"


def test_conceptual_step_has_no_binding(monkeypatch):
    """3. 概念性步骤：target_element_id 为空 → 无 overlay"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", True)

    def _mock_call(query: str, elements: Optional[List[UIElement]] = None, timeout: int = 30, **kwargs):
        return {
            "steps": [
                {"action": "等待下载完成", "description": "请等待下载进度完成", "target_element_id": ""},
            ]
        }, None, 10, "primary", False

    monkeypatch.setattr("server.services.planning.router.call_deepseek", _mock_call)

    response = process_query("等待下载完成")
    step = response.steps[0]
    assert step.target_element_id is None
    assert step.annotation is None


def test_hallucinated_element_id_falls_back(monkeypatch):
    """4. LLM 幻觉 ID：返回不存在的 ~99 → 安全降级为空"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", True)

    def _mock_call(query: str, elements: Optional[List[UIElement]] = None, timeout: int = 30, **kwargs):
        return {
            "steps": [
                {"action": "点击下载", "description": "点击下载按钮", "target_element_id": "~99"},
            ]
        }, None, 10, "primary", False

    monkeypatch.setattr("server.services.planning.router.call_deepseek", _mock_call)

    response = process_query("点击下载按钮")
    step = response.steps[0]
    assert step.target_element_id is None
    assert step.annotation is None


def test_empty_elements_generate_text_only_steps(monkeypatch):
    """5. OmniParser 失败：elements 为空 → 全部生成纯文字步骤"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", True)
    monkeypatch.setattr(
        "server.services.planning.router.SCENARIO_ELEMENTS",
        {"wechat": [], "screenshot": [], "default": []},
    )

    def _mock_call(query: str, elements: Optional[List[UIElement]] = None, timeout: int = 30, **kwargs):
        return {
            "steps": [
                {"action": "观察界面", "description": "查看当前屏幕", "target_element_id": ""},
                {"action": "等待加载", "description": "等待内容加载", "target_element_id": ""},
            ]
        }, None, 10, "primary", False

    monkeypatch.setattr("server.services.planning.router.call_deepseek", _mock_call)

    response = process_query("点击下载按钮")
    assert response.ui_elements == []
    for step in response.steps:
        assert step.target_element_id is None
        assert step.annotation is None


def test_l2_template_skips_gpu_parse(monkeypatch):
    """L2 模板命中时不调用 OmniParser，detection_meta.parse_skipped=true"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", False)

    parse_called = {"n": 0}

    def _fake_parse(_img):
        parse_called["n"] += 1
        from server.services.omniparser_client import ParseResult
        return ParseResult()

    monkeypatch.setattr(
        "server.services.planning.router.parse_screenshot_full", _fake_parse
    )

    response = process_query("怎么截屏", "data:image/png;base64,abc")
    assert parse_called["n"] == 0
    assert response.detection_meta.get("parse_skipped") is True
    assert response.detection_meta.get("route") == "L2"
    assert len(response.steps) >= 2
    assert response.steps[0].interaction == "keyboard"


def test_l2_settings_with_image_runs_parse(monkeypatch):
    """带截图时，非 keyboard 的 L2 模板（如打开设置）应降级 L3 并 parse"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", False)
    # 本用例显式验证「OmniParser 启用」路径；纯视觉模式（OMNIPARSER_ENABLED=false）走 L4
    monkeypatch.setattr(settings, "OMNIPARSER_ENABLED", True)
    monkeypatch.setattr(settings, "ROUTING_MODE", "precision")
    parse_called = {"n": 0}

    def _fake_parse(_img):
        parse_called["n"] += 1
        from server.services.omniparser_client import ParseResult
        return ParseResult(elements=_make_elements())

    monkeypatch.setattr(
        "server.services.planning.router.parse_screenshot_full", _fake_parse
    )

    response = process_query("打开系统设置", "data:image/png;base64,abc")
    assert parse_called["n"] == 1
    assert response.detection_meta.get("parse_skipped") is not True
    assert response.detection_meta.get("route") == "L3"


def test_l2_broad_option_no_match_wps():
    """WPS 合并单元格不应命中「打开设置」类 L2 模板"""
    from server.services.planning.complexity_router import generate_l2_steps

    assert generate_l2_steps("WPS 怎么合并单元格") is None
    assert generate_l2_steps("Excel 合并单元格") is None


def test_l2_keyboard_interaction_flag():
    from server.services.planning.complexity_router import generate_l2_steps

    steps = generate_l2_steps("怎么截屏")
    assert steps is not None
    assert all(s.get("interaction") == "keyboard" for s in steps)
    assert steps[0].get("_l2_keyboard_only") is True


def test_parse_failed_uses_text_llm_not_mock_scenario(monkeypatch):
    """parse 无元素时走纯文本 LLM，不注入 SCENARIO_ELEMENTS mock"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", True)
    monkeypatch.setattr(settings, "ROUTING_MODE", "precision")
    monkeypatch.setattr(
        "server.services.planning.router.generate_l2_steps",
        lambda query, elements=None: None,
    )
    monkeypatch.setattr(
        "server.services.planning.router.parse_screenshot_full",
        lambda _img: __import__(
            "server.services.omniparser_client", fromlist=["ParseResult"]
        ).ParseResult(),
    )
    captured: list = []

    def _mock_llm(query, elements=None, **kwargs):
        captured.append(elements)
        return (
            {
                "steps": [
                    {
                        "action": "文字指引",
                        "description": "无元素纯文本",
                        "target_element_id": "",
                    }
                ]
            },
            None,
            5,
            "deepseek",
            False,
        )

    monkeypatch.setattr("server.services.planning.router.call_deepseek", _mock_llm)

    response = process_query("完成复杂跨应用迁移任务", "data:image/png;base64,abc")
    assert response.detection_meta.get("parse_degraded") is True
    assert captured and captured[0] == []
    assert response.steps[0].target_element_id is None


def test_mock_fallback_uses_predefined_bindings(monkeypatch):
    """6. Mock 降级：USE_REAL_LLM=false → 使用预定义绑定"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", False)
    monkeypatch.setattr(
        "server.services.planning.router.generate_l2_steps",
        lambda query, elements=None: None,
    )

    response = process_query("安装微信")
    steps = response.steps
    assert len(steps) == 4
    # 第一步绑定 Edge 图标
    assert steps[0].target_element_id == "~1"
    assert steps[0].annotation is not None
    # 第二步无绑定
    assert steps[1].target_element_id is None
    assert steps[1].annotation is None
    # 第三步绑定下载按钮
    assert steps[2].target_element_id == "~2"
    assert steps[2].annotation is not None

    # generate_steps 同样返回 mock 数据与约束
    raw_steps, constraints, _ = generate_steps("截图")
    assert len(raw_steps) == 3
    assert raw_steps[0]["action"] == "打开截图工具"
    assert raw_steps[0]["target_element_id"] == "~1"
    assert constraints is None
