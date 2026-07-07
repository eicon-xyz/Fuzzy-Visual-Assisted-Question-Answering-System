"""
HAJIMI Server 测试共享 fixtures
供多 Agent 并行开发期间回归测试使用
"""

from typing import List, Optional
from uuid import uuid4
import json

import pytest

from server.models.schemas import UIElement
from server.services.session.manager import SessionManager


# ═══════════════════════════════════════════════════════════════════════════
# Layer 1/2 通用 Mock/Fake fixtures
# ═══════════════════════════════════════════════════════════════════════════


class FakeBrowser:
    """模拟 BrowserController 的有状态假实现。

    行为接近真实 BrowserController —— navigate 改变内部 URL，
    get_snapshot 读取 _elements，click/type 记录最后操作。
    每个测试用例拿全新实例（scope=function），避免状态污染。
    """

    def __init__(self):
        self.is_started = True
        self._current_url = "about:blank"
        self._page_title = ""
        self._elements: list[dict] = []
        self._last_clicked: Optional[str] = None
        self._last_typed: Optional[tuple[str, str]] = None
        self._scroll_position = 0
        self._last_key: Optional[str] = None
        self._closed = False
        self._navigate_call_count = 0

    def navigate(self, url: str) -> dict:
        self._navigate_call_count += 1
        self._current_url = url
        self._page_title = f"Page at {url}"
        return {
            "success": True,
            "url": url,
            "title": self._page_title,
            "status": 200,
            "wait_until": "commit",
        }

    def get_snapshot(self) -> dict:
        lines = [
            f"## Browser Snapshot",
            f"Title: {self._page_title}",
            f"URL: {self._current_url}",
            f"Interactive elements ({len(self._elements)} shown):",
            "",
        ]
        for i, el in enumerate(self._elements):
            tag_label = el.get("tag", "?")
            text_str = el.get("text", "(no text)")
            sel_str = el.get("selector", "?")
            lines.append(f"  {i}  <{tag_label}> \"{text_str}\"  [{sel_str}]")
        return {
            "success": True,
            "title": self._page_title,
            "url": self._current_url,
            "elements": list(self._elements),
            "snapshot_text": "\n".join(lines),
            "action_summary": f"snapshot: {len(self._elements)} elements on '{self._page_title}'",
        }

    def click(self, selector: str) -> dict:
        self._last_clicked = selector
        return {
            "success": True,
            "selector": selector,
            "tag": "button",
            "text": "Click Me",
            "action_summary": f"clicked {selector}",
        }

    def type(self, selector: str, text: str) -> dict:
        self._last_typed = (selector, text)
        return {
            "success": True,
            "selector": selector,
            "text": text,
            "action_summary": f"typed '{text}' into '{selector}'",
        }

    def scroll(self, direction: str, amount: int = 300) -> dict:
        delta = amount if direction == "down" else -amount
        self._scroll_position += delta
        return {
            "success": True,
            "direction": direction,
            "amount": amount,
            "action_summary": f"scrolled {direction} {amount}px",
        }

    def screenshot(self) -> dict:
        return {
            "success": True,
            "image_b64": "data:image/jpeg;base64,FAKE_JPEG_DATA",
            "action_summary": "browser screenshot taken",
        }

    def press_key(self, keys: str) -> dict:
        self._last_key = keys
        return {
            "success": True,
            "keys": keys,
            "action_summary": f"pressed '{keys}' in browser",
        }

    def close(self) -> None:
        self._closed = True
        self.is_started = False


class MockLLMResponse:
    """可编程的 LLM 响应工厂。支持三种模式：

    - canned: 返回预置 JSON 字符串（默认）
    - sequence: 依次返回列表中的多个响应（模拟多轮对话）
    - passthrough: 透传到真实 LLM（Layer 3 用，需环境变量配置）
    """

    def __init__(self, mode="canned", responses=None):
        self.mode = mode
        self.responses = responses or []
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        if self.mode == "passthrough":
            from server.services.llm.providers import call_llm as _real

            return _real(*args, **kwargs)
        if not self.responses:
            return ""
        resp = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return resp


@pytest.fixture
def fresh_session():
    """每个测试用例拿到一个全新的 SessionManager 实例。"""
    return SessionManager(session_id=f"test_{uuid4().hex[:8]}")


@pytest.fixture
def fake_browser():
    """有状态的假浏览器，scope=function，每个测试全新实例。"""
    return FakeBrowser()


@pytest.fixture
def mock_llm():
    """Layer 1/2 默认使用：返回固定 JSON，不调用真实 LLM。"""
    return MockLLMResponse(mode="canned", responses=[
        json.dumps({
            "__tool_call__": True,
            "name": "mark_step_done",
            "arguments": {"reason": "test completed"},
        })
    ])


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
