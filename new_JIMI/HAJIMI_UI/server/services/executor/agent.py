"""
Execution Agent — LLM-driven tool-calling loop for each step.

The LLM observes the screen via get_screen_info, decides which tool to call,
executes via element_id (never coordinates), verifies, and marks step done/failed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Optional

import pyautogui
import pyperclip

from server.config import settings
from server.models.schemas import ExecutedStep, UIElement
from server.services.browser.controller import BrowserController
from server.services.executor.safety import check_step
from server.services.llm.providers import extract_json_object
from server.services.omniparser_client import (
    _filter_elements_for_llm,
    parse_screenshot_full,
)
from server.services.memory.retriever import get_retriever

logger = logging.getLogger(__name__)

MAX_TOOL_CALL_ROUNDS = getattr(settings, "MAX_TOOL_CALL_ROUNDS", None) or 15

EXECUTION_SYSTEM_PROMPT = """你是桌面自动化执行专家。你的任务是完成当前步骤。你可以调用工具来观察屏幕和执行操作。

## 可用工具
- launch_app(app_name): 通过系统级命令启动应用（Win+搜索）。当步骤为打开应用时，优先使用此工具。
- get_screen_info(): 获取当前屏幕的元素列表（返回 id, content, left_ids, right_ids, top_ids, bottom_ids）
- click(element_id): 单击指定元素
- double_click(element_id): 双击指定元素。桌面图标、文件通常需要双击打开。
- type_text(element_id, text): 点击元素后输入文本
- press_key(keys): 按键盘组合键，如 "enter", "ctrl+v", "win"
- scroll(direction, amount): 滚轮滚动
- wait(seconds): 等待指定秒数，让界面响应
- mark_step_done(reason): 标记当前步骤已完成。如果步骤的前置条件已满足（如应用已打开、搜索框已聚焦），直接调用此工具并说明 reason="precondition already satisfied"。
- mark_step_failed(reason): 标记步骤失败并说明原因

## 工作流程
1. 如果当前步骤是打开某个应用，直接调用 launch_app(app_name)，不需要先 get_screen_info
2. 否则，首先调用 get_screen_info 观察当前屏幕
3. 如果当前步骤的前置条件已满足（参考 previous_steps 中的 action_summary），直接调用 mark_step_done
4. 在元素列表中定位目标（匹配 content 文本）
5. 调用 click / double_click / type_text 等执行操作
6. 验证操作结果（见下方验证标准）
7. 确认完成后调用 mark_step_done

## 警告：element_id 生命周期
调用 get_screen_info 后，所有之前的 element_id 立即失效。你必须基于最新一次返回的元素列表选择目标。不得引用之前调用的 element_id。如果工具返回 "element_id not found in current screen"，你必须重新调用 get_screen_info。

## 元素定位策略
- 优先精确匹配 content 文本
- 匹配不唯一时，利用空间关系：如"搜索框右边的按钮" → 找 left_ids 包含搜索框 id 的元素
- 内容可能部分匹配（如搜索框显示"搜"而非"搜索"）
- 找不到时，先 wait(2) 再重新 get_screen_info

## 验证标准
- type_text 成功后（返回 success=true），这本身就是验证——不需要再次 get_screen_info
- click 后验证：观察屏幕元素列表是否有变化（新元素出现、元素消失、content 变化）
- 如果连续 2 次 get_screen_info 结果完全相同，说明上一步操作可能无效，应尝试替代方案
- 桌面图标、文件操作使用 double_click 而非 click

## 异常处理
- 点击后无反应 → wait(1) 后重试
- 元素始终找不到 → 尝试 press_key("tab") 切换焦点再试
- 意外弹窗 → 优先点击关闭/取消按钮（content 为 "关闭"/"取消"/"跳过"/"×" 的元素）
- 多次重试无效 → mark_step_failed
- 弹窗遮挡目标元素 → 先关闭弹窗再继续

## 效率约束
- 连续调用 get_screen_info 是无意义的——如果上一次返回了同样的元素，不需要再调一次
- 优先基于上一次 get_screen_info 返回的元素列表直接操作，不要反复截屏
- 一段操作（如点击后等待然后验证）最多调用 1 次 get_screen_info
- wait 工具用于等待页面加载，调用 wait 后通常不需要立即再调 get_screen_info——先尝试操作

## 禁止事项
- 禁止假设屏幕上看不到的元素存在
- 禁止在一次响应中调用多个工具（串行调用，每次只调一个）
- 禁止跳过 get_screen_info 直接操作（除非只是按键等待）
- 禁止在 get_screen_info 之后引用之前的 element_id

## 浏览器工具（browser_ 前缀）
当需要操作网页时，优先使用 browser_ 前缀的工具。它们基于 DOM 操作，比视觉点击更精确：
- browser_navigate(url): 导航到网页。首次使用浏览器时，会自动启动浏览器。
- browser_snapshot(): 获取页面结构化元素列表（链接、按钮、输入框等），不是完整HTML。用于观察页面。
- browser_click(selector): 点击元素。selector 用 snapshot 返回的 CSS 选择器，或 text=匹配文本。
- browser_type(selector, text): 在输入框输入文本。
- browser_scroll(direction, amount): 滚轮翻页。
- browser_close(): 关闭浏览器窗口。
- browser_screenshot(): 截取当前浏览器页面的屏幕截图，用于视觉验证。
- browser_press_key(keys): 在浏览器中按键盘按键。如'Enter'提交搜索、'Escape'关闭弹窗。

### 浏览器工作流程
1. 如果当前步骤涉及网页操作，先调用 browser_navigate 打开目标网址
2. 然后调用 browser_snapshot 查看页面有哪些可交互元素
3. 根据 snapshot 返回的 selector 信息，调用 browser_click / browser_type 执行操作
4. 必要时再次 browser_snapshot 验证结果
5. 步骤完成后，如果后续不再需要浏览器，调用 browser_close 释放资源。

### 视觉验证
- 当需要判断页面是否显示了预期内容时，使用 browser_screenshot
- browser_screenshot 返回的是 JPEG 图片的 base64 编码，前端可以展示截图
- snapshot 用于定位元素 + 点击；screenshot 的 image_b64 字段可供前端渲染展示
- 对于结构验证（如'搜索结果是否出现'），优先使用 browser_snapshot 查看元素列表"""


# ═══════════════════════════════════════════════════════════════════════════
# Tool definitions (OpenAI function-calling format)
# ═══════════════════════════════════════════════════════════════════════════


def _build_tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "launch_app",
                "description": "通过Win+搜索启动应用程序。当步骤为打开应用时优先使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "要启动的应用名称，如'网易云音乐'、'Calculator'",
                        }
                    },
                    "required": ["app_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_screen_info",
                "description": "截取当前屏幕并通过OmniParser获取元素列表。返回元素的id、content和空间关系。每次调用会刷新element_map，旧的element_id全部失效。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "click",
                "description": "单击指定元素。传入element_id而非坐标。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {
                            "type": "string",
                            "description": "元素ID，来自get_screen_info返回列表中的id字段",
                        }
                    },
                    "required": ["element_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "double_click",
                "description": "双击指定元素。桌面图标和文件通常需要双击。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string", "description": "元素ID"}
                    },
                    "required": ["element_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "type_text",
                "description": "点击元素获取焦点后，通过剪贴板粘贴文本（支持中文输入）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {
                            "type": "string",
                            "description": "目标输入框的元素ID",
                        },
                        "text": {"type": "string", "description": "要输入的文本"},
                    },
                    "required": ["element_id", "text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "press_key",
                "description": "按键盘组合键。如'enter'、'ctrl+v'、'win'。多个键用+号连接。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "string",
                            "description": "组合键字符串，如 'enter' 或 'ctrl+v'",
                        }
                    },
                    "required": ["keys"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scroll",
                "description": "滚轮滚动。direction: 'up'或'down'。amount: 滚动量（1=一行）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["up", "down"]},
                        "amount": {"type": "integer", "description": "滚动量，默认3"},
                    },
                    "required": ["direction"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "wait",
                "description": "等待指定秒数，让界面响应。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "seconds": {"type": "number", "description": "等待秒数"}
                    },
                    "required": ["seconds"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mark_step_done",
                "description": "标记当前步骤已成功完成。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "完成原因，如'操作成功'或'precondition already satisfied'",
                        }
                    },
                    "required": ["reason"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mark_step_failed",
                "description": "标记当前步骤失败。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "失败原因"}
                    },
                    "required": ["reason"],
                },
            },
        },
        # ── Browser tools ──
        {
            "type": "function",
            "function": {
                "name": "browser_navigate",
                "description": "浏览器导航到指定URL。打开网页后使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要导航到的URL，如'https://baidu.com'",
                        }
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_snapshot",
                "description": "获取当前网页的精简DOM结构（仅交互元素：链接、按钮、输入框等），不返回完整HTML。用于观察页面状态。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_click",
                "description": "在浏览器中点击指定元素。传入CSS选择器或文本匹配。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "CSS选择器，如'#submit'、'.btn'、'text=登录'",
                        }
                    },
                    "required": ["selector"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_type",
                "description": "在浏览器输入框中输入文本。先清空再输入。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "输入框的CSS选择器",
                        },
                        "text": {"type": "string", "description": "要输入的文本"},
                    },
                    "required": ["selector", "text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_scroll",
                "description": "滚轮滚动页面。direction: 'up'或'down'。amount: 滚动像素量（默认300）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["up", "down"]},
                        "amount": {
                            "type": "integer",
                            "description": "滚动像素量，默认300",
                        },
                    },
                    "required": ["direction"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_close",
                "description": "关闭浏览器窗口。任务完成后调用以释放资源。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_screenshot",
                "description": "对当前浏览器页面截图，返回base64 JPEG。用于视觉验证页面状态（如'搜索结果是否出现'）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_press_key",
                "description": "在浏览器页面中按键盘按键。如'Enter'提交搜索、'Escape'关闭弹窗、'Tab'切换焦点。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "string",
                            "description": "按键名，如'Enter'、'Escape'、'Tab'、'PageDown'",
                        }
                    },
                    "required": ["keys"],
                },
            },
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Context builder
# ═══════════════════════════════════════════════════════════════════════════


def _build_context_for_llm(
    goal: str,
    current_step: dict,
    previous_steps: list[dict],
) -> str:
    """Build the context string passed to the LLM each turn."""
    parts = [f"## 任务目标\n{goal}\n"]

    if previous_steps:
        parts.append("## 已完成的步骤")
        for ps in previous_steps:
            parts.append(
                f"- Step {ps['index']}: {ps['instruction']} "
                f"→ {ps.get('action_summary', 'done')}"
            )

    parts.append(
        f"## 当前步骤\nStep {current_step['index']}: {current_step['instruction']}"
    )
    parts.append("\n请完成当前步骤。你可以调用工具。每次只调用一个工具。")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Execution Agent
# ═══════════════════════════════════════════════════════════════════════════


class ExecutionAgent:
    """LLM-driven execution loop for one step at a time."""

    def __init__(self):
        self.element_map: dict[str, UIElement] = {}
        self.screen_elements: list[dict] = []
        self.tools = _build_tool_definitions()
        self._browser: Optional[BrowserController] = None

    @property
    def browser(self) -> BrowserController:
        """Lazy-init BrowserController — created on first browser_xxx tool call."""
        if self._browser is None:
            self._browser = BrowserController()
        return self._browser

    def _get_or_create_browser_loop(self) -> asyncio.AbstractEventLoop:
        """Lazy-init a dedicated event loop in a daemon thread.

        Playwright objects (browser, page, CDP session) are bound to the
        event loop that created them.  Using asyncio.run() per-call would
        create+destroy a loop each time, causing "Event loop is closed"
        and "object belongs to different event loop" errors.

        Instead we create ONE persistent loop running in its own daemon
        thread, and every browser coroutine is submitted to it via
        run_coroutine_threadsafe.  The loop lives as long as the
        ExecutionAgent instance.
        """
        if getattr(self, "_browser_loop", None) is None:
            self._browser_loop = asyncio.new_event_loop()
            self._browser_loop_thread = threading.Thread(
                target=self._browser_loop.run_forever, daemon=True
            )
            self._browser_loop_thread.start()
            logger.info("Browser event loop thread started")
        return self._browser_loop

    def _run_async(self, coro):
        """Run an async coroutine synchronously on the persistent browser loop.

        Thread-safe: can be called from any thread.  Submits the coroutine
        to the dedicated browser event loop and blocks until completion.

        Defensive: if the loop has died for any reason, tears it down and
        creates a fresh one, then retries once.
        """
        loop = self._get_or_create_browser_loop()
        if loop.is_closed():
            logger.warning("Browser event loop was closed; recreating")
            self._browser_loop = None
            loop = self._get_or_create_browser_loop()

        try:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=120)
        except (RuntimeError, BrokenPipeError, ConnectionError) as e:
            # Loop may have crashed — recreate and retry once
            logger.warning("Browser event loop error (%s); recreating", e)
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
            self._browser_loop = None
            self._browser = None  # force re-create so start() runs in new loop
            loop = self._get_or_create_browser_loop()
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=120)

    def _stop_browser_loop(self) -> None:
        """Stop the dedicated browser event loop thread. Idempotent."""
        loop = getattr(self, "_browser_loop", None)
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        if getattr(self, "_browser_loop_thread", None) is not None:
            self._browser_loop_thread.join(timeout=5)
        self._browser_loop = None
        self._browser_loop_thread = None

    def _ensure_browser_started(self) -> None:
        """Lazy-start the browser on first use."""
        if not self.browser.is_started:
            self._run_async(self.browser.start(headless=False))

    def close_browser(self) -> None:
        """Close browser and clean up. Safe to call multiple times."""
        if self._browser is not None and self._browser.is_started:
            try:
                self._run_async(self._browser.close())
            except Exception as e:
                logger.warning("Error closing browser during cleanup: %s", e)
        self._browser = None
        self._stop_browser_loop()

    def clear_element_map(self):
        self.element_map = {}
        self.screen_elements = []
        self._get_screen_call_count = 0
        self._last_screen_ids = None

    # ── Tool implementations ──

    def _do_get_screen_info(self) -> dict:
        """Screenshot → OmniParser → rebuild element_map."""
        # Wake up potentially frozen RDP/remote GUI session before screenshot
        try:
            import pyautogui

            pyautogui.press("esc")
            time.sleep(0.2)
        except Exception:
            pass

        try:
            from core.screen_capture import capture_to_base64

            image_b64 = capture_to_base64(exclude_self=True, fmt="JPEG")
        except ImportError:
            # Fallback: use mss directly
            import base64
            from io import BytesIO

            import mss
            from PIL import Image

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                img = sct.grab(monitor)
                pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                buf = BytesIO()
                pil.save(buf, format="JPEG", quality=70)
                image_b64 = (
                    "data:image/jpeg;base64,"
                    + base64.b64encode(buf.getvalue()).decode()
                )

        parse_result = parse_screenshot_full(image_b64, compute_spatial=False)
        self.element_map = {e.element_id: e for e in parse_result.elements}
        self.screen_elements = _filter_elements_for_llm(parse_result.elements)

        result = {
            "success": True,
            "elements": [
                {"id": el["id"], "content": el["content"]}
                for el in self.screen_elements
                if el.get("content") and el["content"].strip()
            ][:30],
            "element_count": len(self.screen_elements),
            "action_summary": f"screenshot taken ({len(self.screen_elements)} elements)",
        }
        # Include annotated screenshot so the frontend can display visual updates
        if parse_result.annotated_image:
            result["annotated_image"] = parse_result.annotated_image
        # Warn LLM after 3+ screen calls AND detect near-duplicate screens
        self._get_screen_call_count = getattr(self, "_get_screen_call_count", 0) + 1
        this_ids = frozenset(self.element_map.keys())
        prev_ids = getattr(self, "_last_screen_ids", None)
        if prev_ids is not None and this_ids:
            overlap = len(this_ids & prev_ids) / max(len(this_ids | prev_ids), 1)
            if overlap > 0.8:
                result["warning"] = (
                    f"⚠️ 屏幕与上一次截图几乎相同 ({overlap:.0%} 元素重叠)。"
                    "连续截屏不会改变画面。请立即基于当前元素列表点击目标或 mark_step_done/mark_step_failed。"
                )
        self._last_screen_ids = this_ids
        if self._get_screen_call_count >= 3:
            result["warning"] = (
                f"已连续调用 get_screen_info {self._get_screen_call_count} 次。"
                "屏幕元素不会因为反复截屏而改变。请立即根据已有元素决定下一步操作："
                "点击目标元素、输入文本、或调用 mark_step_done/mark_step_failed。"
            )
        return result

    def _do_launch_app(self, app_name: str) -> dict:
        safety = check_step(f"launch app '{app_name}'")
        if safety.level == "red":
            return {
                "success": False,
                "error": f"launch blocked (zone: red): {safety.reason}",
            }
        if safety.level == "yellow":
            return {
                "success": False,
                "error": f"launch requires confirmation (zone: yellow): {safety.reason}",
            }

        # App name normalization: translate common Chinese names to their
        # Windows Search executables for reliable Win+Search matching.
        # Without this, Windows Search may not find the app when pasting
        # Chinese text (e.g. "计算器" may not match "Calculator.lnk").
        # The canonical mapping table lives in server.services.launcher.APP_EXECUTABLE_MAP
        from server.services.launcher import APP_EXECUTABLE_MAP, launch_app

        search_name = APP_EXECUTABLE_MAP.get(app_name, app_name)
        if search_name != app_name:
            logger.info(f"App name mapped: '{app_name}' → '{search_name}'")

        result = launch_app(search_name)
        return {
            "success": result.get("success", False),
            "app_name": app_name,
            "action_summary": f"launched app '{app_name}' (tier {result.get('tier', '?')})",
        }

    def _do_click(self, element_id: str, double: bool = False) -> dict:
        element = self.element_map.get(element_id)
        if element is None:
            return {
                "success": False,
                "error": f"element_id '{element_id}' not found in current screen. "
                f"Please call get_screen_info() again.",
            }

        cx, cy = element.center
        safety = check_step(f"click element {element.text}")
        if safety.level == "red":
            return {
                "success": False,
                "error": f"action blocked (zone: red): {safety.reason}",
            }
        if safety.level == "yellow":
            return {
                "success": False,
                "error": f"action requires confirmation (zone: yellow): {safety.reason}. "
                f"Choose a different target or try an alternative approach.",
            }

        pyautogui.moveTo(cx, cy, duration=0.2)
        time.sleep(0.1)
        clicks = 2 if double else 1
        pyautogui.click(clicks=clicks)

        label = "double-clicked" if double else "clicked"
        return {
            "success": True,
            "clicked": element_id,
            "content": element.text,
            "action_summary": f"{label} element '{element.text}'",
        }

    def _do_type_text(self, element_id: str, text: str) -> dict:
        element = self.element_map.get(element_id)
        if element is None:
            return {
                "success": False,
                "error": f"element_id '{element_id}' not found in current screen. "
                f"Please call get_screen_info() again.",
            }

        cx, cy = element.center
        safety = check_step(f"type '{text}' into element")
        if safety.level == "red":
            return {
                "success": False,
                "error": f"action blocked (zone: red): {safety.reason}",
            }
        if safety.level == "yellow":
            return {
                "success": False,
                "error": f"action requires confirmation (zone: yellow): {safety.reason}. "
                f"Choose a different target or try an alternative approach.",
            }

        old_clipboard = pyperclip.paste()
        try:
            pyautogui.click(cx, cy)
            time.sleep(0.2)
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)  # ensure paste completes (Electron/VM apps may be slow)
        finally:
            pyperclip.copy(old_clipboard)

        return {
            "success": True,
            "typed": text,
            "into": element_id,
            "action_summary": f"typed '{text}' into '{element.text}'",
        }

    def _do_press_key(self, keys: str) -> dict:
        safety = check_step(f"press key '{keys}'")
        if safety.level == "red":
            return {
                "success": False,
                "error": f"key blocked (zone: red): {safety.reason}",
            }
        if safety.level == "yellow":
            return {
                "success": False,
                "error": f"key requires confirmation (zone: yellow): {safety.reason}",
            }
        key_list = [k.strip() for k in keys.split("+")]
        if len(key_list) == 1:
            pyautogui.press(key_list[0])
        else:
            pyautogui.hotkey(*key_list)
        return {"success": True, "keys": keys, "action_summary": f"pressed '{keys}'"}

    def _do_scroll(self, direction: str, amount: int = 3) -> dict:
        amt = amount if direction == "up" else -amount
        pyautogui.scroll(amt)
        return {
            "success": True,
            "direction": direction,
            "amount": amount,
            "action_summary": f"scrolled {direction} x{amount}",
        }

    # ── Tool dispatcher ──

    def dispatch_tool(self, tool_name: str, tool_args: dict) -> dict:
        """Execute a tool call and return the result dict."""
        if tool_name == "get_screen_info":
            return self._do_get_screen_info()
        elif tool_name == "launch_app":
            return self._do_launch_app(tool_args.get("app_name", ""))
        elif tool_name == "click":
            return self._do_click(tool_args.get("element_id", ""))
        elif tool_name == "double_click":
            return self._do_click(tool_args.get("element_id", ""), double=True)
        elif tool_name == "type_text":
            return self._do_type_text(
                tool_args.get("element_id", ""),
                tool_args.get("text", ""),
            )
        elif tool_name == "press_key":
            return self._do_press_key(tool_args.get("keys", "enter"))
        elif tool_name == "scroll":
            return self._do_scroll(
                tool_args.get("direction", "down"),
                tool_args.get("amount", 3),
            )
        elif tool_name == "wait":
            secs = float(tool_args.get("seconds", 1.0))
            time.sleep(secs)
            return {
                "success": True,
                "waited": secs,
                "action_summary": f"waited {secs}s",
            }
        elif tool_name == "mark_step_done":
            return {
                "__step_complete__": True,
                "success": True,
                "reason": tool_args.get("reason", ""),
            }
        elif tool_name == "mark_step_failed":
            return {"__step_failed__": True, "reason": tool_args.get("reason", "")}
        # ── Browser tools ──
        elif tool_name == "browser_navigate":
            self._ensure_browser_started()
            return self._run_async(self.browser.navigate(tool_args.get("url", "")))
        elif tool_name == "browser_snapshot":
            self._ensure_browser_started()
            return self._run_async(self.browser.get_snapshot())
        elif tool_name == "browser_click":
            self._ensure_browser_started()
            return self._run_async(
                self.browser.click(tool_args.get("selector", ""))
            )
        elif tool_name == "browser_type":
            self._ensure_browser_started()
            return self._run_async(
                self.browser.type(
                    tool_args.get("selector", ""),
                    tool_args.get("text", ""),
                )
            )
        elif tool_name == "browser_scroll":
            self._ensure_browser_started()
            return self._run_async(
                self.browser.scroll(
                    tool_args.get("direction", "down"),
                    tool_args.get("amount", 300),
                )
            )
        elif tool_name == "browser_close":
            if self._browser is not None and self._browser.is_started:
                self._run_async(self.browser.close())
            return {"success": True, "action_summary": "browser closed"}
        elif tool_name == "browser_screenshot":
            self._ensure_browser_started()
            return self._run_async(self.browser.screenshot())
        elif tool_name == "browser_press_key":
            self._ensure_browser_started()
            return self._run_async(
                self.browser.press_key(tool_args.get("keys", "Enter"))
            )
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    # ── Single-step execution ──

    def execute_step(
        self,
        step: ExecutedStep,
        goal: str,
        previous_steps: list[dict],
        cancel_event: Optional[threading.Event] = None,
        on_screenshot: Optional[callable] = None,
    ) -> ExecutedStep:
        """Run the agent loop for a single step.

        Args:
            step: The step to execute (instruction populated, action/target/params empty)
            goal: Overall task goal from Planning Agent
            previous_steps: List of completed step dicts with action_summary
            cancel_event: Threading event set by user cancellation
            on_screenshot: Optional callback(b64_str) when a new screenshot is taken.
                Called from the agent loop thread after each get_screen_info.

        Returns:
            ExecutedStep with action, target_element_id, params, action_summary, status filled
        """
        step.status = "executing"
        self.clear_element_map()

        current_step_info = {"index": step.step_index, "instruction": step.instruction}
        context = _build_context_for_llm(goal, current_step_info, previous_steps)

        action_summary = None
        consecutive_empty = 0

        # Build the conversation once: system prompt + task context.
        # Tool call history accumulates across rounds below.
        # Build system prompt with user memory (if available)
        system_content = EXECUTION_SYSTEM_PROMPT
        try:
            retriever = get_retriever()
            user_memory = retriever.retrieve(
                user_id="default",
                query=goal,
                element_count=None,  # Element count not available at this point
            )
            if user_memory:
                system_content = EXECUTION_SYSTEM_PROMPT + "\n\n" + user_memory
        except Exception:
            pass  # Memory retrieval failure should not block execution

        messages = [{"role": "system", "content": system_content}]
        # Add a hint: if the step is just about launching an app, the LLM should
        # call launch_app then mark_step_done directly, not verify via get_screen_info
        if (
            "打开" in step.instruction
            or "启动" in step.instruction
            or "launch" in step.instruction.lower()
            or "open" in step.instruction.lower()
        ):
            context += "\n\n注意：如果本步骤只是打开/启动一个应用，用 launch_app 打开后请立即调用 mark_step_done，无需 get_screen_info 验证。"
        messages.append({"role": "user", "content": context})

        for round_num in range(MAX_TOOL_CALL_ROUNDS):
            if cancel_event and cancel_event.is_set():
                step.status = "failed"
                step.action_summary = "cancelled by user"
                return step

            # On subsequent rounds, nudge the LLM to continue
            if round_num > 0:
                messages.append(
                    {
                        "role": "user",
                        "content": "继续。你还可以调用工具。每次只调用一个工具。",
                    }
                )
                time.sleep(1.5)  # throttle OmniParser load

            # Call LLM with tool definitions
            try:
                raw, assistant_msg = self._call_llm_with_tools(messages)
                # DEBUG: if raw is empty but assistant has tool_calls, something is wrong
                if not raw and assistant_msg and assistant_msg.get("tool_calls"):
                    logger.error(
                        f"BUG: raw is empty but assistant_msg has tool_calls! msg={assistant_msg}"
                    )
                    tc = assistant_msg["tool_calls"][0]
                    func = tc["function"]
                    raw = json.dumps(
                        {
                            "__tool_call__": True,
                            "name": func["name"],
                            "arguments": (
                                json.loads(func["arguments"])
                                if isinstance(func["arguments"], str)
                                else func["arguments"]
                            ),
                        }
                    )
            except Exception as e:
                logger.error(f"LLM call failed at round {round_num}: {e}")
                step.status = "failed"
                step.action_summary = f"LLM error: {e}"
                return step

            # Parse tool call from LLM response
            tool_name, tool_args = self._parse_tool_call(raw)
            if tool_name is None:
                # In auto mode, LLM may respond with text instead of a tool call.
                # Reject text-only responses that don't advance the task.
                if raw and raw.strip():
                    logger.warning(
                        f"LLM returned text-only response (no tool call): {raw[:300]}"
                    )
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": "请直接使用工具来执行操作或标记完成（如 mark_step_done），不要只用文字描述。调用一个工具。",
                        }
                    )
                    continue
                consecutive_empty += 1
                logger.warning(
                    f"LLM returned non-tool response ({consecutive_empty}/3): {raw[:200]}"
                )
                if consecutive_empty >= 3:
                    step.status = "failed"
                    step.action_summary = (
                        "LLM returned empty response 3 times consecutively"
                    )
                    return step
                # Feed the response back as context
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": "请调用一个工具。每次只调用一个工具。可用工具: get_screen_info, click, type_text, press_key, mark_step_done, mark_step_failed 等。",
                    }
                )
                continue
            else:
                consecutive_empty = 0

            # Dispatch tool
            result = self.dispatch_tool(tool_name, tool_args)
            logger.info(
                f"Round {round_num}: {tool_name}({tool_args}) → success={result.get('success')}"
            )

            # If the tool took a screenshot, push it to the frontend
            if tool_name == "get_screen_info" and on_screenshot:
                annotated = result.get("annotated_image")
                if annotated:
                    try:
                        on_screenshot(annotated)
                    except Exception:
                        pass

            # Check for step completion signals
            if result.get("__step_complete__"):
                step.status = "done"
                step.action_summary = action_summary or result.get(
                    "reason", "step completed"
                )
                return step
            if result.get("__step_failed__"):
                step.status = "failed"
                step.action_summary = result.get("reason", "step failed")
                return step

            # Accumulate action_summary from tool returns
            if result.get("action_summary"):
                action_summary = result["action_summary"]

            # Add assistant message + tool result to conversation using the original
            # assistant message (with real tool_calls) so OpenAI API can match the
            # tool_call_id in the subsequent role:tool message.
            # The tool_call_id MUST match the id in the assistant's tool_calls array.
            if assistant_msg and assistant_msg.get("tool_calls"):
                tool_call_id = assistant_msg["tool_calls"][0]["id"]
                messages.append(assistant_msg)
            else:
                tool_call_id = f"call_{round_num}"
                messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

        # Exhausted all rounds
        logger.warning(
            f"Step {step.step_index} exhausted {MAX_TOOL_CALL_ROUNDS} rounds"
        )
        step.status = "failed"
        step.action_summary = "exceeded max tool calls"
        return step

    def _call_llm_with_tools(self, messages: list[dict]) -> tuple[str, Optional[dict]]:
        """Call LLM with function-calling tools. Returns (raw_response_text, original_assistant_msg)."""
        pc = self._get_provider_config()
        base = pc["base_url"].rstrip("/")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {pc['api_key']}",
        }
        body = {
            "model": pc["model"],
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0.2,
            "tools": self.tools,
            "tool_choice": "auto",
        }
        import httpx

        url = f"{base}/chat/completions"
        with httpx.Client(timeout=120) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            msg = choice["message"]
            # Check for tool_calls in response
            if msg.get("tool_calls"):
                tc = msg["tool_calls"][0]
                func = tc["function"]
                return (
                    json.dumps(
                        {
                            "__tool_call__": True,
                            "name": func["name"],
                            "arguments": (
                                json.loads(func["arguments"])
                                if isinstance(func["arguments"], str)
                                else func["arguments"]
                            ),
                        }
                    ),
                    msg,
                )  # return the original assistant message for conversation threading
            content = msg.get("content", "") or ""
            # V4 Flash may return content alongside tool_calls (finish_reason=tool_calls
            # but content also present). Parse content as fallback tool call.
            if content:
                # Try to extract function-call-like text from content
                try:
                    parsed = extract_json_object(content)
                    if "name" in parsed and "arguments" in parsed:
                        synthetic_id = "call_from_content"
                        return json.dumps(
                            {
                                "__tool_call__": True,
                                "name": parsed["name"],
                                "arguments": parsed["arguments"],
                            }
                        ), {  # synthetic assistant_msg with valid tool_calls
                            "role": "assistant",
                            "content": content,
                            "tool_calls": [
                                {
                                    "id": synthetic_id,
                                    "type": "function",
                                    "function": {
                                        "name": parsed["name"],
                                        "arguments": json.dumps(
                                            parsed["arguments"], ensure_ascii=False
                                        ),
                                    },
                                }
                            ],
                        }
                except Exception:
                    pass
                # Content present but not parseable as tool — return as raw for caller to handle
                return content, None
            return "", None

    def _parse_tool_call(self, raw: str) -> tuple[Optional[str], dict]:
        """Parse tool call from LLM response. Returns (tool_name, args_dict)."""
        try:
            data = json.loads(raw)
            if data.get("__tool_call__"):
                return data["name"], data.get("arguments", {})
        except json.JSONDecodeError:
            pass
        # Fallback: try to extract function-call-like JSON from raw text
        try:
            parsed = extract_json_object(raw)
            if "name" in parsed and "arguments" in parsed:
                return parsed["name"], parsed.get("arguments", {})
            if "tool" in parsed:
                return parsed["tool"], parsed.get("args", parsed.get("params", {}))
        except Exception:
            pass
        return None, {}

    @staticmethod
    def _get_provider_config() -> dict:
        from server.services.llm.providers import _get_provider_config

        return _get_provider_config()
