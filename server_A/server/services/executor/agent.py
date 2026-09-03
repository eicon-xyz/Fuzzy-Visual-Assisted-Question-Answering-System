"""
Execution Agent — LLM-driven tool-calling loop for each step.

The LLM observes the screen via get_screen_info, decides which tool to call,
executes via element_id (never coordinates), verifies, and marks step done/failed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from typing import Optional

import pyautogui
import pyperclip

from server.config import settings
from server.models.schemas import ExecutedStep, UIElement
from server.services import eval_telemetry as et
from server.services.browser.controller import BrowserController
from server.services.executor.safety import check_step
from server.services.llm.providers import extract_json_object
from server.services.omniparser_client import (
    _filter_elements_for_llm,
    parse_screenshot_full,
)
from server.services.memory.retriever import get_retriever

logger = logging.getLogger(__name__)

MAX_TOOL_CALL_ROUNDS = getattr(settings, "MAX_TOOL_CALL_ROUNDS", None) or 50

_LLM_STRIP_KEYS = ("annotated_image", "image_b64")


def _strip_for_llm(result: dict) -> dict:
    """进 LLM messages 前剥离仅供前端渲染的图字段（deepseek-chat 是文本模型）。"""
    if not isinstance(result, dict):
        return result
    if not any(k in result for k in _LLM_STRIP_KEYS):
        return result
    return {k: v for k, v in result.items() if k not in _LLM_STRIP_KEYS}


EXECUTION_SYSTEM_PROMPT = """你是桌面自动化执行专家。你的任务是完成当前步骤。你可以调用工具来观察屏幕和执行操作。

## 可用工具
- launch_app(app_name): 通过系统级命令启动应用（Win+搜索）。当步骤为打开应用时，优先使用此工具。
- get_screen_info(): 获取当前屏幕控件投影列表，字段：id / type(控件类型) / name(控件文本) / class(框架类名) / enabled(是否可用) / patterns(可用交互模式: invoke,value,toggle,selectionitem,expandcollapse) / bbox(相对窗口左上角 [左,上,宽,高] 像素)。附带 window_title 与 window_size
- click(element_id, name[, expect]): 单击指定元素（UIA 绑定优先：Invoke/Select 等精确模式；失败回退坐标点击）。name 必填=该元素的 name 字段，服务端交叉验证防幻觉点击；expect 可选，声明期望的界面变化
- double_click(element_id, name[, expect]): 双击指定元素。桌面图标、文件通常需要双击打开。
- paste_text(text[, expect]): 将文本粘贴到当前获得焦点的位置（通过剪贴板）。启动应用后或点击输入框后，文本会自动粘贴到光标所在位置，不需要 element_id。用于无法检测到输入框的场景（如记事本文本区、聊天输入框等纯文本区域）。
- type_text(element_id, name, text[, expect]): 向输入元素输入文本（UIA 绑定优先：ValuePattern.SetValue 精确设置）
- press_key(keys): 按键盘组合键，如 "enter", "ctrl+v", "win"
- scroll(direction, amount): 滚轮滚动
- wait(seconds): 等待指定秒数，让界面响应
- mark_step_done(reason, evidence): 标记当前步骤已完成。evidence 必填：来自屏幕观察/动作验证的独立事实（如窗口标题变化、控件文本/value 变化），无证据会被拒收。如果步骤的前置条件已满足（如应用已打开、搜索框已聚焦），观察确认后可调用此工具并说明 reason="precondition already satisfied"
- mark_step_failed(reason): 标记步骤失败（第一次会被拦下要求换策略再试，第二次生效）
- report_infeasible(reason, tried): 环境/权限/红线下确实做不到时显式终止并回报原因（必须先试过≥2种策略）
- ask_user(question): 需要用户提供信息或决策（登录、选择、授权）时向用户提问，不要瞎猜也不要卡死在这

## 工作流程
1. 如果当前步骤是打开某个应用，直接调用 launch_app(app_name)，不需要先 get_screen_info
2. 否则，首先调用 get_screen_info 观察当前屏幕
3. 如果当前步骤的前置条件已满足（参考 previous_steps 中的 action_summary），直接调用 mark_step_done
4. 在元素列表中定位目标（匹配 content 文本）
5. 调用 click / double_click / type_text 等执行操作
6. 验证操作结果（见下方验证标准）
7. 确认完成后调用 mark_step_done，evidence 写支持判定的屏幕事实（不是"我觉得完成了"）

## 警告：element_id 生命周期
调用 get_screen_info 后，所有之前的 element_id 立即失效。你必须基于最新一次返回的元素列表选择目标。不得引用之前调用的 element_id。如果工具返回 "element_id not found in current screen"，你必须重新调用 get_screen_info。

## 元素定位策略
- 元素来自 Windows UI Automation 结构化采集，每个元素带 type/name/class/enabled/patterns/bbox 投影字段
- 优先按 name 精确/部分匹配目标文本（如目标"搜索框"可能显示为"搜"）
- 用 type+patterns 判定控件性质：输入框=edit+value，按钮=button+invoke，菜单项=menuitem，复选框=checkbox/toggle
- 跳过 enabled=false 的控件（点了不会生效）
- 同名多控件时用 bbox 区分：bbox=[左,上,宽,高] 为相对窗口左上角像素，"左边的按钮"→ 取左值小者，"顶部菜单"→ 取上值小者，"第 N 行"→ 按上值排序
- 找不到时，先 wait(2) 再重新 get_screen_info
- 调用 click/double_click/type_text 时必须同时传 name 参数（你选定条目的 name 值）：服务端会拿它与快照核对，若该 id 实际不是你说的控件会拒绝执行并回报真实名称——按真名重新决策，不要重复同一个错误 id
- 菜单/下拉框（type=menu/menuitem/combobox，或 patterns 含 expandcollapse）：直接 click 会自动走 ExpandCollapse 展开，并返回展开后的新选项列表（new_elements，旧 id 失效）——从中选第二级目标再 click，禁止用坐标盲点菜单
- click 返回 action_ambiguous/pattern_failed 时：pattern_failed 说明动作可能已部分生效，先观察再决策，严禁原样补刀；action_ambiguous 说明选错控件类型，换 type_text/press_key 或换控件，最后手段才是显式传 via="coordinate"

## 验证标准
- 动作下发前服务端自动做 actionability 预检（可见/启用/位置稳定/不被遮挡，在超时内轮询等待条件而非固定等待）；预检不过返回 error_code=not_actionable + missing_predicates——界面在加载就 wait 后重试，控件不可用就换 enabled 的同功能控件，不要硬点同一个 id
- 动作工具（click/double_click/type_text/paste_text）会自动做动作后验证，返回：
  action_ok（动作是否送达）、verified（控件是否仍可用且在屏内）、state_changed（控件属性是否变化）、prop_diff（变化明细）
- 对界面状态有把握的动作用 expect 参数声明期望（如 click(确定, expect="已发送")），服务端在调用内轮询验证；expect_ok=false 时结果会附 new_elements（自动重观察），旧 id 全部失效
- type_text 返回 state_changed=true 即输入已生效（value 属性变化），无需再次 get_screen_info
- 若动作返回 verified=false 且 state_changed=false（界面毫无变化），说明点击/输入未生效：基于返回的 new_elements 换目标或换策略，不要原样重试
- 桌面图标、文件操作使用 double_click 而非 click

## 异常处理
- 工具失败时返回固定结构 {ok:false, error_code, message, hint}——先读 hint，按它的建议自纠，不要无视错误码原样重试
- 点击后无反应 → wait(1) 后重试
- 元素始终找不到 → 尝试 press_key("tab") 切换焦点再试
- 意外弹窗 → 优先点击关闭/取消按钮（content 为 "关闭"/"取消"/"跳过"/"×" 的元素）
- 多次重试无效 → 换全新策略再试；仍无效才 mark_step_failed；环境根本做不到 → report_infeasible；需要人来决策/提供信息 → ask_user（WebArena 数据：过半"失败"其实是过早放弃，别提前躺平）
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
                "description": "获取当前屏幕控件投影列表（UIA 结构化采集）。每个元素含 id/type/name/class/enabled/patterns/bbox(相对窗口像素)。每次调用会刷新 element_map，旧的 element_id 全部失效。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "click",
                "description": "单击指定元素。传入element_id而非坐标，并同时传入该元素在get_screen_info中的name（服务端与快照交叉核对，不符则拒绝执行并回报真实名称，防止幻觉点击）。若元素是菜单/下拉（支持 ExpandCollapse），自动改为展开并返回展开后的新选项列表。返回含动作后验证结果（action_ok/verified/state_changed/prop_diff），若界面未变化会自动重观察并返回新元素列表。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {
                            "type": "string",
                            "description": "元素ID，来自get_screen_info返回列表中的id字段",
                        },
                        "name": {
                            "type": "string",
                            "description": "你认为该元素的名称（列表中对应条目的 name），用于 id×name 交叉验证",
                        },
                        "expect": {
                            "type": "string",
                            "description": "可选：点击后期望出现的界面文本（新控件名/窗口标题片段），服务端在调用内轮询验证（WaitFor 语义），不满足会自动重观察",
                        },
                        "via": {
                            "type": "string",
                            "enum": ["coordinate"],
                            "description": "仅在目标控件无任何交互模式且确需像素点击时传 'coordinate'（自绘/游戏类 UI）。默认禁止——自动坐标回退已移除。",
                        },
                    },
                    "required": ["element_id", "name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "double_click",
                "description": "双击指定元素。桌面图标和文件通常需要双击。name 用于 id×name 交叉验证。返回含动作后验证结果。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string", "description": "元素ID"},
                        "name": {
                            "type": "string",
                            "description": "该元素在列表中的 name（交叉验证）",
                        },
                        "expect": {
                            "type": "string",
                            "description": "可选：双击后期望出现的界面文本（如新窗口标题片段），服务端轮询验证",
                        },
                    },
                    "required": ["element_id", "name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "paste_text",
                "description": "将文本粘贴到当前获得焦点的位置（通过剪贴板）。不需要 element_id，适用于记事本文本区、聊天输入框等检测不到输入框的场景。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "要粘贴的文本",
                        },
                        "expect": {
                            "type": "string",
                            "description": "可选：粘贴后期望出现的界面文本，服务端轮询验证",
                        },
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "type_text",
                "description": "向指定输入元素输入文本（UIA ValuePattern.SetValue 优先，失败回退剪贴板粘贴）。name 用于 id×name 交叉验证。返回含动作后验证结果（state_changed 即输入框 value 变化）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {
                            "type": "string",
                            "description": "目标输入框的元素ID",
                        },
                        "name": {
                            "type": "string",
                            "description": "该输入元素在列表中的 name（交叉验证）",
                        },
                        "text": {"type": "string", "description": "要输入的文本"},
                        "expect": {
                            "type": "string",
                            "description": "可选：输入后期望出现的界面文本（如联想词条），服务端轮询验证",
                        },
                    },
                    "required": ["element_id", "text", "name"],
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
                "description": "标记当前步骤已成功完成。必须提供 evidence（可独立核查的完成证据，如界面观察到的控件文本/状态变化、动作返回的 state_changed/expect_ok）——无证据会被拒收并要求补充。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "完成原因，如'操作成功'或'precondition already satisfied'",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "支持完成判定的具体屏幕证据（来自最新 get_screen_info/动作验证结果的事实描述，如「窗口标题变为'无标题 - 记事本'」「搜索框 value 已含目标文本」）",
                        },
                    },
                    "required": ["reason", "evidence"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mark_step_failed",
                "description": "标记当前步骤失败并说明原因。第一次调用会被拦下要求先换一种策略重试（防过早放弃）；确认无路可走时第二次调用即生效。若需要用户决策请改用 ask_user，环境/权限根本做不到请改用 report_infeasible。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "失败原因"}
                    },
                    "required": ["reason"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "report_infeasible",
                "description": "显式判定当前步骤在当前环境/权限/红线约束下不可行，终止本任务并回报原因。必须先真正尝试过至少 2 种不同策略。用于替代 mark_step_failed 表达'做不到'而非'没做到'，防止假失败。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "为什么不可行（环境缺什么/触碰哪条红线/需要什么权限）",
                        },
                        "tried": {
                            "type": "string",
                            "description": "已尝试过的策略列表（简述），证明不是提前放弃",
                        },
                    },
                    "required": ["reason", "tried"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ask_user",
                "description": "当需要用户提供信息/决策（如登录凭据、二选一方案、敏感操作授权）时调用，步骤暂停并把问题回传用户。不要用它逃避可自己解决的困难。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "要问用户的问题（简明、可直接回答）",
                        }
                    },
                    "required": ["question"],
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
# 0.4 零 LLM 卡死检测（browser-use 阈值分级 + OpenHands stuck 规则子集）
# ═══════════════════════════════════════════════════════════════════════════


class _LoopDetector:
    """动作哈希滑窗重复检测 + UIA 观测指纹停滞检测 + 连续失败计数。

    纯代码零 LLM 成本；触阈值后不改写执行结果，只分级改写回灌给
    LLM 的 nudge 提示（提醒不阻断，与 browser-use 同策略）。
    """

    WINDOW = 20            # 动作滑窗（browser-use window=20）
    REPEAT_L1 = 5          # 同一动作重复 5 次：提示换思路
    REPEAT_L2 = 8          # 8 次：强制换策略
    REPEAT_L3 = 12         # 12 次：熔断级 nudge
    STAGNATION_OBS = 5     # 观测指纹连续 N 次不变 = 界面停滞
    FAIL_STREAK = 3        # 连续 N 次工具失败（OpenHands 3×Error 规则）

    def __init__(self, events: Optional[dict] = None) -> None:
        from collections import deque

        self._recent = deque(maxlen=self.WINDOW)
        self._last_fp: Optional[str] = None
        self._same_obs = 0
        self._fail_streak = 0
        # T1 遥测：阈值越界事件计数（可注入步遥测的 loop_events 字典，就地累加）
        self.events = (
            events
            if events is not None
            else {
                "repeat5": 0,
                "repeat8": 0,
                "repeat12": 0,
                "stagnation": 0,
                "replan": 0,
            }
        )
        self._repeat_flag = 0  # 上次越过的最高重复档（1/2/3），回落清零

    @staticmethod
    def action_key(tool: str, args: dict) -> str:
        try:
            payload = json.dumps(
                {tool: args}, sort_keys=True, ensure_ascii=False, default=str
            )
        except Exception:
            payload = str(tool)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def observation_fingerprint(elements: list) -> str:
        """观测指纹：元素语义内容（type/name/bbox 或 id/content）的 sha256。

        比「id 集合」更稳——UIA element_id 每次快照重编号（u1..uN），
        内容不变时指纹不变，正是停滞检测所需。
        """
        rows = sorted(
            "{}|{}|{}".format(
                e.get("type", ""),
                e.get("name", e.get("content", "")),
                e.get("bbox", ""),
            )
            for e in elements
        )
        return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]

    def record_action(self, tool: str, args: dict, success: bool) -> None:
        if tool == "wait":  # 纯等待不是无效重复
            return
        self._recent.append(self.action_key(tool, args))
        self._fail_streak = self._fail_streak + 1 if not success else 0

    def record_observation(self, elements: Optional[list]) -> None:
        if not elements:
            return
        fp = self.observation_fingerprint(elements)
        if fp == self._last_fp:
            self._same_obs += 1
        else:
            self._same_obs = 0
        self._last_fp = fp

    def repeat_count(self) -> int:
        """最近一次动作在滑窗内连续出现的次数（从尾部数）。"""
        if not self._recent:
            return 0
        last = self._recent[-1]
        n = 0
        for h in reversed(self._recent):
            if h != last:
                break
            n += 1
        return n

    def build_nudge(self) -> str:
        """当前轮应注入的 nudge 文本；无异常返回空串。

        T1 遥测：每次「越过」阈值记一次事件（持续处于阈值内不重复计数，
        回落后再次越过会再记，用于评测台统计卡死检测的实际触发次数）。
        """
        parts: list[str] = []
        n = self.repeat_count()
        tier = 3 if n >= self.REPEAT_L3 else 2 if n >= self.REPEAT_L2 else 1 if n >= self.REPEAT_L1 else 0
        if tier > self._repeat_flag:
            key = {1: "repeat5", 2: "repeat8", 3: "repeat12"}[tier]
            self.events[key] = self.events.get(key, 0) + 1
        if tier == 0:
            self._repeat_flag = 0
        elif tier > self._repeat_flag:
            self._repeat_flag = tier
        if n >= self.REPEAT_L3:
            parts.append(
                f"⛔ 同一动作已重复 {n} 次，已判定卡死。禁止再次调用相同工具与参数："
                "要么换完全不同的路径（不同控件/press_key/菜单），要么立即 "
                "mark_step_failed 并说明尝试过什么。"
            )
        elif n >= self.REPEAT_L2:
            parts.append(
                f"⚠️ 同一动作已连续 {n} 次且任务未推进。下一步必须改变方案："
                "换目标元素、换交互方式（double_click/press_key/type_text）或重新观察。"
            )
        elif n >= self.REPEAT_L1:
            parts.append(
                f"注意：同一动作已连续 {n} 次。若上次返回 state_changed=false 或 "
                "expect_ok=false，请勿原样重复，先换策略。"
            )
        stag = self._same_obs >= self.STAGNATION_OBS
        if stag and not getattr(self, "_stag_flag", False):
            self.events["stagnation"] = self.events.get("stagnation", 0) + 1
        self._stag_flag = stag
        if stag:
            parts.append(
                f"界面观测指纹已连续 {self._same_obs + 1} 次观察完全相同——环境停滞。"
                "反复观察不会改变画面，执行一个完全不同的动作或承认步骤失败。"
            )
        replan = self._fail_streak >= self.FAIL_STREAK
        if replan and not getattr(self, "_replan_flag", False):
            self.events["replan"] = self.events.get("replan", 0) + 1
        self._replan_flag = replan
        if replan:
            parts.append(
                f"连续 {self._fail_streak} 次工具调用失败（OpenHands 级联失败规则）。"
                "REPLAN SUGGESTED：不要在失效假设上继续，重新观察并重排本步骤做法。"
            )
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
        self._uia = None  # lazy: server.services.executor.uia_bridge.UIABridge
        self.screen_source: Optional[str] = None  # "uia" | "omniparser" | "none"
        self._reset_step_ledger()  # 0.7 证据账本（每步在 execute_step 再重置）
        self._step_tel: Optional[dict] = None  # T1 步遥测（execute_step 内新建）

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
        """Lazy-start the browser on first use. Auto-recover if page was closed."""
        if not self.browser.is_started:
            self._run_async(self.browser.start(headless=False))
        # If page was closed by a previous LLM action, recreate it
        if self._browser is not None:
            try:
                page = self._browser._page if hasattr(self._browser, '_page') else None
                if page is not None and page.is_closed():
                    logger.warning("Browser page was closed externally, recreating...")
                    self._browser._started = False
                    self._run_async(self._browser.start(headless=False))
            except Exception:
                pass

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
        self.screen_source = None
        if getattr(self, "_uia", None) is not None:
            self._uia.clear()

    # ── 0.7 done 证据化：步骤级证据账本 ──

    # 动作类工具：成功执行即记入证据账本（browser_* 同权）
    _MUTATING_TOOLS = (
        "click",
        "double_click",
        "type_text",
        "paste_text",
        "press_key",
        "scroll",
        "launch_app",
        "browser_navigate",
        "browser_click",
        "browser_type",
        "browser_press_key",
        "browser_scroll",
    )

    def _reset_step_ledger(self) -> None:
        self._action_evidence: list[dict] = []
        self._observation_count = 0
        self._done_attempts = 0
        self._failed_attempts = 0

    def _record_evidence(self, tool_name: str, result: dict) -> None:
        """把成功的动作/观察记入本步证据账本。"""
        if not isinstance(result, dict):
            return
        if tool_name == "get_screen_info" and result.get("ok"):
            self._observation_count = getattr(self, "_observation_count", 0) + 1
            return
        if tool_name in self._MUTATING_TOOLS and result.get("ok"):
            self._action_evidence.append(
                {
                    "tool": tool_name,
                    "target": str(
                        result.get("content")
                        or result.get("into")
                        or result.get("keys")
                        or result.get("app_name")
                        or result.get("url")
                        or tool_name
                    )[:60],
                    "state_changed": result.get("state_changed"),
                    "verified": result.get("verified"),
                    "via": result.get("via"),
                }
            )

    def _strong_evidence(self) -> Optional[dict]:
        """最强证据：属性实际变化(state_changed) > 校验通过(verified) > 其他成功动作。"""
        ev = getattr(self, "_action_evidence", [])
        for e in ev:
            if e.get("state_changed"):
                return e
        for e in ev:
            if e.get("verified"):
                return e
        return ev[-1] if ev else None

    def _gate_mark_step_done(self, reason: str, evidence: str) -> Optional[dict]:
        """done 证据化 gate。返回 None=放行；返回 dict=拒收（带 hint）。

        放行条件（任一）：
          a) 本步有成功动作且其中存在 state_changed/verified 的独立证据；
          b) LLM 显式提交了 evidence 描述（≥8 字）且本步至少观察过一次；
          c) reason 为“前置条件已满足”且有观察记录；
          d) 本步已有成功的 launch_app/browser_navigate（应用/页面级证据）；
          e) 已拒收过一次（防死锁：第二次放行，但结果标注 unverified_done）。
        """
        self._done_attempts = getattr(self, "_done_attempts", 0) + 1
        if self._done_attempts >= 2:
            return None
        strong = self._strong_evidence()
        if strong is not None and (
            strong.get("state_changed") or strong.get("verified")
        ):
            return None
        if len((evidence or "").strip()) >= 8 and getattr(self, "_observation_count", 0) >= 1:
            return None
        if (
            "precondition" in (reason or "").lower()
            and getattr(self, "_observation_count", 0) >= 1
        ):
            return None
        if any(
            e["tool"] in ("launch_app", "browser_navigate")
            for e in getattr(self, "_action_evidence", [])
        ):
            return None
        return {
            "ok": False,
            "success": False,
            "error_code": "done_without_evidence",
            "error": "mark_step_done 被拒收：本步骤尚无可独立核查的完成证据。",
            "hint": (
                "完成判定不能只靠自评。请任选其一："
                "1) 用带 expect 的动作工具拿到 state_changed/expect_ok=true 的结果；"
                "2) 重新 get_screen_info，把支持结论的屏幕事实（窗口标题/控件文本变化）"
                "写进 evidence 参数再调 mark_step_done；"
                "3) 若确实无法完成，调用 mark_step_failed 或 report_infeasible 说明原因。"
                f"本步已有动作记录：{[e['tool'] + ':' + e['target'] for e in getattr(self, '_action_evidence', [])][:8]}"
            ),
        }

    def _gate_mark_step_failed(self, reason: str) -> Optional[dict]:
        """防过早放弃：mark_step_failed 第一次调用给一次'换策略'机会。"""
        self._failed_attempts = getattr(self, "_failed_attempts", 0) + 1
        if self._failed_attempts >= 2:
            return None
        return {
            "ok": False,
            "success": False,
            "error_code": "giveup_refused_retry",
            "error": "mark_step_failed 暂被拦下：按 WebArena 教训，过早放弃比多试一次贵得多。",
            "hint": (
                "最后再试一条不同的路径：换控件（按 type/patterns/bbox 重新选）、"
                "换交互方式（press_key/菜单展开/滚动后再看）、或先 wait 再观察。"
                "需要人工决策→ask_user；确认环境做不到→report_infeasible。"
                "若你仍坚持，再调一次 mark_step_failed 即生效。"
            ),
        }

    # ── Tool implementations ──

    def _get_uia(self) -> "UIABridge":
        """Lazy-init UIA 桥（UIA 绑定，非 Windows/未安装自动降级为空）。"""
        if getattr(self, "_uia", None) is None:
            from server.services.executor.uia_bridge import UIABridge

            self._uia = UIABridge()
        return self._uia

    @staticmethod
    def _names_match(expected: str, actual: str) -> bool:
        """0.3 id×name 交叉验证的匹配规则：精确/双向包含（大小写不敏感）。"""
        e = (expected or "").strip().lower()
        a = (actual or "").strip().lower()
        if not e:
            return True
        return e == a or e in a or a in e

    def _name_guard(self, element_id: str, name: Optional[str]) -> Optional[dict]:
        """防幻觉点击（UFO _verify_id 同款）：动作参数带的 name 与最新快照
        实际控件名核对，不符返回拒绝结果并回报真名；通过返回 None。"""
        if not name:
            return None  # 未提供 name 不阻断（schema 已引导必带）
        element = self.element_map.get(element_id)
        actual = (element.text or "").strip() if element is not None else ""
        if not actual:
            # 无名控件：无法交叉验证，放行但提醒
            return {"name_unverifiable": f"控件 '{element_id}' 无文本名，未做 id×name 核对"}
        if self._names_match(name, actual):
            return None
        return {
            "success": False,
            "error": (
                f"NAME_MISMATCH: element_id '{element_id}' 的实际名称是「{actual}」，"
                f"不是「{name}」——目标定位与实际控件不符，动作已拒绝执行。"
            ),
            "actual_name": actual,
            "hint": (
                f"请核对元素列表：'{name}' 可能对应其它 id，"
                f"或调用 get_screen_info 重新观察后再选择；不要改用 id 碰运气。"
            ),
        }

    def _post_action_result(
        self,
        base: dict,
        r: dict,
        expect: Optional[str] = None,
    ) -> dict:
        """把 uia_bridge.act 的验证链结果并入工具返回（0.2 动作后验证接线）。

        验证失败（verify 未过且属性无变化，或 expect 未满足）→ 自动重观察，
        返回新元素列表让 LLM 基于最新状态决策，而不是带着失效假设继续。
        """
        base["action_ok"] = bool(r.get("action_ok"))
        base["verified"] = r.get("verified")
        base["state_changed"] = r.get("state_changed")
        if r.get("prop_diff"):
            base["prop_diff"] = r["prop_diff"]
        if expect:
            base["expect_ok"] = r.get("expect_ok")
            base["expect_detail"] = r.get("expect_detail")

        verify_failed = base["verified"] is False and not base.get("state_changed")
        expect_failed = bool(expect) and r.get("expect_ok") is False
        if verify_failed or expect_failed:
            # 自动重观察：刷新 element_map，把新元素附在结果里
            obs = self._do_get_screen_info()
            base["reobserved"] = True
            base["ids_refreshed"] = True
            base["new_elements"] = obs.get("elements")
            why = (
                f"期望条件「{expect}」未出现"
                if expect_failed
                else f"动作后控件校验未通过（{r.get('verify_reason', '')}）"
            )
            base["hint"] = (
                f"{why}，已自动重新观察屏幕（上方 new_elements 是最新元素列表，"
                "旧 element_id 全部失效）。请基于新列表改变策略重试，或 mark_step_failed。"
            )
        return base

    _SCREEN_PROJECTION_LIMIT = 40

    def _prioritize_projection(self, proj: list[dict]) -> list[dict]:
        """0.1 感知序列化：投影字段替代旧 {id,content}×30 截断。

        优先级：可交互 patterns > 白名单类型 > 有名字 > 可用状态；
        截断后按快照（DFS）顺序重排，保持空间阅读顺序。
        """
        if len(proj) <= self._SCREEN_PROJECTION_LIMIT:
            return proj

        def _score(item: dict) -> int:
            return (
                (4 if item.get("patterns") else 0)
                + (2 if item.get("enabled") else 0)
                + (1 if item.get("name") else 0)
            )

        ranked = sorted(enumerate(proj), key=lambda p: -_score(p[1]))
        picked = sorted(ranked[: self._SCREEN_PROJECTION_LIMIT], key=lambda p: p[0])
        out = []
        for _, item in picked:
            entry = {
                "id": item["id"],
                "type": item["type"],
                "name": item["name"],
                "enabled": item["enabled"],
            }
            if item.get("class"):
                entry["class"] = item["class"]
            if item.get("patterns"):
                entry["patterns"] = item["patterns"]
            entry["bbox"] = item["bbox"]
            out.append(entry)
        return out

    def _do_get_screen_info(self) -> dict:
        """屏幕感知：UIA 结构化采集优先 → OmniParser 兜底 → 明确空结果。

        0.5：删除观察前向系统按 ESC 的全局副作用——它会把刚展开的
        菜单/下拉直接关掉；需要关弹窗时用显式 press_key("esc")。
        """
        # 1) UIA 优先（主感知通道：结构化投影，非截扁的 id+content）
        uia = self._get_uia()
        if uia.available:
            _t_snap = time.perf_counter()
            uia_elements = uia.snapshot()
            _snap_ms = (time.perf_counter() - _t_snap) * 1000
            if uia_elements:
                et.tally_snapshot(
                    self._step_tel, _snap_ms, len(uia.last_projection())
                )
                self.element_map = {e.element_id: e for e in uia_elements}
                self.screen_elements = _filter_elements_for_llm(uia_elements)
                self.screen_source = "uia"
                proj = uia.last_projection()
                visible = self._prioritize_projection(proj)
                result = {
                    "success": True,
                    "source": "uia",
                    "elements": visible,
                    "element_count": len(proj),
                    "action_summary": f"UIA 结构化采集（{len(proj)} 个控件，展示 {len(visible)} 个）",
                }
                if len(visible) < len(proj):
                    result["truncated"] = len(proj) - len(visible)
                win = uia.window_title()
                if win:
                    result["window_title"] = win
                rect = getattr(uia, "_last_window_rect", None)
                if rect:
                    result["window_size"] = [rect[2] - rect[0], rect[3] - rect[1]]
                # 附带截图供前端展示视觉更新（无标注框）
                try:
                    from core.screen_capture import capture_to_base64

                    result["annotated_image"] = capture_to_base64(
                        exclude_self=True, fmt="JPEG"
                    )
                except Exception:
                    pass
                self._get_screen_call_count = getattr(
                    self, "_get_screen_call_count", 0
                ) + 1
                self._last_screen_ids = frozenset(self.element_map.keys())
                if self._get_screen_call_count >= 3:
                    result["warning"] = (
                        f"已连续调用 get_screen_info {self._get_screen_call_count} 次。"
                        "屏幕元素不会因为反复截屏而改变。请立即根据已有元素决定下一步操作："
                        "点击目标元素、输入文本、或调用 mark_step_done/mark_step_failed。"
                    )
                return result

        # 2) OmniParser 兜底（仅 OMNIPARSER_ENABLED=true 时）
        if getattr(settings, "OMNIPARSER_ENABLED", True):
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
            self.screen_source = "omniparser"

            result = {
                "success": True,
                "source": "omniparser",
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
            self._get_screen_call_count = getattr(
                self, "_get_screen_call_count", 0
            ) + 1
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

        # 3) 无 UIA、无 OmniParser：给出可操作提示
        self.element_map = {}
        self.screen_elements = []
        self.screen_source = None
        return {
            "success": True,
            "source": "none",
            "elements": [],
            "element_count": 0,
            "warning": "无法获取屏幕元素：UIA 无可用控件，且 OmniParser/视觉兜底未配置。"
            "可尝试 launch_app / press_key / wait，或 mark_step_done / mark_step_failed。",
        }

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

    def _do_click(
        self,
        element_id: str,
        double: bool = False,
        expect: Optional[str] = None,
        name: Optional[str] = None,
        via: Optional[str] = None,
    ) -> dict:
        element = self.element_map.get(element_id)
        if element is None:
            return {
                "success": False,
                "error": f"element_id '{element_id}' not found in current screen. "
                f"Please call get_screen_info() again.",
            }

        # 0.3 id×name 交叉验证：拒绝幻觉点击
        guard = self._name_guard(element_id, name)
        name_warning = None
        if guard is not None:
            if guard.get("success") is False:
                return guard
            name_warning = guard.get("name_unverifiable")

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

        # UIA 绑定优先：决策表选模式（B2）→ 显式 via 才走坐标
        if getattr(self, "screen_source", None) == "uia":
            action = "double_click" if double else "click"
            r = self._get_uia().act(element_id, action=action, expect=expect, via=via)
            if r.get("success"):
                via = r.get("via") or "coord"
                label = "双击" if double else "单击"
                base = {
                    "success": True,
                    "clicked": element_id,
                    "content": element.text,
                    "via": via,
                    "action_summary": f"{label} 元素 '{element.text}'（{via}）",
                }
                if name_warning:
                    base["warning"] = name_warning
                base = self._post_action_result(base, r, expect)
                # 0.5 菜单=展开→自动重观察→再选择：ExpandCollapse 展开后
                # 浮层选项不在旧快照里，必须立刻刷新并把新列表交给 LLM。
                if via == "uia_expand" and not base.get("reobserved"):
                    obs = self._do_get_screen_info()
                    base["expanded"] = True
                    base["ids_refreshed"] = True
                    base["new_elements"] = obs.get("elements")
                    base["hint"] = (
                        "已通过 ExpandCollapse 展开菜单/下拉框，下方 new_elements 是"
                        "展开后的最新选项列表（旧 element_id 全部失效）。"
                        "请从中选择目标项再次 click，不要点坐标。"
                    )
                return base
            return {
                "success": False,
                "error": f"UIA 操作失败: {r.get('error')}",
                "via": r.get("via"),
                "action_ok": False,
                # 0.8 actionability 拒绝等带码错误原样透传（error_code/hint）
                "error_code": r.get("error_code"),
                "hint": r.get("hint"),
            }

        cx, cy = element.center
        pyautogui.moveTo(cx, cy, duration=0.2)
        time.sleep(0.1)
        clicks = 2 if double else 1
        pyautogui.click(clicks=clicks)

        label = "double-clicked" if double else "clicked"
        base = {
            "success": True,
            "clicked": element_id,
            "content": element.text,
            "via": "coord",
            "action_ok": True,
            "action_summary": f"{label} element '{element.text}'",
        }
        if expect:
            uia = self._get_uia()
            if uia.available:
                w = uia.wait_for_text(expect, timeout=4.0)
                base["expect_ok"] = bool(w.get("ok"))
                base["expect_detail"] = w
                if not w.get("ok"):
                    base["hint"] = (
                        f"坐标点击后期望「{expect}」未出现，请 get_screen_info 重观察"
                        "并改变策略。"
                    )
        return base

    def _do_paste_text(self, text: str, expect: Optional[str] = None) -> dict:
        """Paste text via clipboard into the currently focused element.
        No element_id needed — uses the current window focus.
        """
        safety = check_step(f"paste '{text}'")
        if safety.level == "red":
            return {
                "success": False,
                "error": f"paste blocked (zone: red): {safety.reason}",
            }
        if safety.level == "yellow":
            return {
                "success": False,
                "error": f"paste requires confirmation (zone: yellow): {safety.reason}. "
                f"Choose a different target or try an alternative approach.",
            }

        old_clipboard = pyperclip.paste()
        try:
            pyperclip.copy(text)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
        finally:
            pyperclip.copy(old_clipboard)

        base = {
            "success": True,
            "text": text,
            "action_ok": True,
            "action_summary": f"pasted text into focused window",
        }
        if expect:
            uia = self._get_uia()
            if uia.available:
                w = uia.wait_for_text(expect, timeout=4.0)
                base["expect_ok"] = bool(w.get("ok"))
                base["expect_detail"] = w
                if not w.get("ok"):
                    base["hint"] = (
                        f"粘贴后期望「{expect}」未出现，请 get_screen_info 重观察并改变策略。"
                    )
        return base

    def _do_type_text(
        self,
        element_id: str,
        text: str,
        expect: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict:
        element = self.element_map.get(element_id)
        if element is None:
            return {
                "success": False,
                "error": f"element_id '{element_id}' not found in current screen. "
                f"Please call get_screen_info() again.",
            }

        # 0.3 id×name 交叉验证：拒绝幻觉输入
        guard = self._name_guard(element_id, name)
        if guard is not None and guard.get("success") is False:
            return guard

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

        # UIA 绑定优先：ValuePattern.SetValue → 焦点+剪贴板
        if getattr(self, "screen_source", None) == "uia":
            r = self._get_uia().act(element_id, action="type", text=text, expect=expect)
            if r.get("success"):
                base = {
                    "success": True,
                    "typed": text,
                    "into": element_id,
                    "via": r.get("via"),
                    "action_summary": f"typed '{text}' into '{element.text}'（{r.get('via')}）",
                }
                return self._post_action_result(base, r, expect)
            return {
                "success": False,
                "error": f"UIA 输入失败: {r.get('error')}",
                "via": r.get("via"),
                "action_ok": False,
                "error_code": r.get("error_code"),  # 0.8 not_actionable 透传
                "hint": r.get("hint"),
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

        base = {
            "success": True,
            "typed": text,
            "into": element_id,
            "via": "coord",
            "action_ok": True,
            "action_summary": f"typed '{text}' into '{element.text}'",
        }
        if expect:
            uia = self._get_uia()
            if uia.available:
                w = uia.wait_for_text(expect, timeout=4.0)
                base["expect_ok"] = bool(w.get("ok"))
                base["expect_detail"] = w
                if not w.get("ok"):
                    base["hint"] = (
                        f"输入后期望「{expect}」未出现，请 get_screen_info 重观察并改变策略。"
                    )
        return base

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

    # 0.6 错误契约：error_code → 面向 LLM 下一轮自纠的默认 hint
    _ERROR_HINTS = {
        "element_not_found": (
            "element_id 不在当前快照（每次观察后旧 id 全部失效）。"
            "先 get_screen_info，再基于最新列表的 id+name 重新选择目标。"
        ),
        "name_mismatch": (
            "目标 id 与名称不符：按回报的真实名称换 id，"
            "或 get_screen_info 后按 name/type/bbox 重新定位。禁止换 id 碰运气。"
        ),
        "blocked_redline": (
            "该动作命中红线，重试不会改变结果。改用不触碰红线的路径；"
            "若任务必须此操作，调用 report_infeasible 说明原因。"
        ),
        "confirm_required": (
            "黄线动作需要用户确认。先尝试无风险的替代路径；"
            "确属必要时调用 ask_user 请求用户批准，不要绕过。"
        ),
        "action_failed": (
            "动作下发失败。get_screen_info 确认控件仍存在，"
            "然后换交互方式（double_click / press_key / 菜单展开）再试。"
        ),
        "action_ambiguous": (
            "该控件类型没有可用的交互模式（按钮/菜单等语义不适用），点不动。"
            "输入框改用 type_text；菜单/下拉先尝试展开；确属自绘/无 pattern 控件"
            "且必须像素点击时，才显式传 via='coordinate'；或重新观察换目标。"
        ),
        "pattern_failed": (
            "选定交互模式执行失败，且动作可能已部分生效。严禁原样补刀重试——"
            "先 get_screen_info 确认界面实际状态（动作可能已生效）再决策换目标/换策略。"
        ),
        "unknown_tool": "工具名不存在，只能使用工具列表中列出的工具。",
        "tool_exception": (
            "工具执行抛出异常。换一条更简单的路径完成本步骤"
            "（避免同一调用重复触发该异常）。"
        ),
        "unknown_error": (
            "查看返回的 message 定位原因；必要时 get_screen_info 重新观察后调整策略。"
        ),
    }

    @staticmethod
    def _classify_error_code(err_text: str) -> str:
        e = (err_text or "").lower()
        if "not found in current screen" in e or "not found" in e and "element" in e:
            return "element_not_found"
        if "name_mismatch" in e:
            return "name_mismatch"
        if "zone: red" in e or "blocked (zone" in e:
            return "blocked_redline"
        if "zone: yellow" in e or "requires confirmation" in e:
            return "confirm_required"
        if "pattern_failed" in e:
            return "pattern_failed"
        if "action_ambiguous" in e:
            return "action_ambiguous"
        if "uia 操作失败" in err_text or "uia 输入失败" in err_text or "failed:" in e:
            return "action_failed"
        if "unknown tool" in e:
            return "unknown_tool"
        if "tool exception" in e:
            return "tool_exception"
        return "unknown_error"

    def _normalize_tool_result(self, tool_name: str, result) -> dict:
        """统一工具返回契约：{ok, error_code, message, hint} + 原有字段。

        成功：ok=true、error_code/message/hint 为 None。
        失败：error_code 枚举分类，hint 给出下一轮自纠建议（面向 LLM）。
        保留 success 字段作向后兼容别名。
        """
        if result is None:
            result = {"success": False, "error": f"tool '{tool_name}' returned None"}
        if not isinstance(result, dict):
            result = {"success": True, "action_summary": str(result)[:300]}
        ok = bool(result.get("success"))
        result["ok"] = ok
        # 控制信号（done/failed/infeasible/ask_user 判定等）不算错误
        if ok or result.get("__step_failed__") or result.get("__step_infeasible__") or result.get("__ask_user__"):
            result.setdefault("error_code", None)
            result.setdefault("message", None)
            result.setdefault("hint", None)
            return result
        err = result.get("error") or result.get("reason") or ""
        code = result.get("error_code") or self._classify_error_code(str(err))
        result["error_code"] = code
        result["message"] = str(err)
        hint = result.get("hint")  # 底层已给更具体的 hint 时不覆盖
        result["hint"] = hint or self._ERROR_HINTS.get(code, self._ERROR_HINTS["unknown_error"])
        return result

    def dispatch_tool(self, tool_name: str, tool_args: dict) -> dict:
        """Execute a tool call. 0.6：所有出口统一 {ok, error_code, message, hint} 契约。"""
        try:
            result = self._dispatch_tool_inner(tool_name, tool_args or {})
        except Exception as exc:
            logger.exception("tool %s raised", tool_name)
            result = {
                "success": False,
                "error": f"tool exception: {type(exc).__name__}: {exc}",
                "error_code": "tool_exception",
            }
        result = self._normalize_tool_result(tool_name, result)
        self._record_evidence(tool_name, result)  # 0.7 证据账本
        return result

    def _dispatch_tool_inner(self, tool_name: str, tool_args: dict) -> dict:
        if tool_name == "get_screen_info":
            return self._do_get_screen_info()
        elif tool_name == "launch_app":
            return self._do_launch_app(tool_args.get("app_name", ""))
        elif tool_name == "click":
            return self._do_click(
                tool_args.get("element_id", ""),
                expect=tool_args.get("expect"),
                name=tool_args.get("name"),
                via=tool_args.get("via"),
            )
        elif tool_name == "double_click":
            return self._do_click(
                tool_args.get("element_id", ""),
                double=True,
                expect=tool_args.get("expect"),
                name=tool_args.get("name"),
            )
        elif tool_name == "type_text":
            return self._do_type_text(
                tool_args.get("element_id", ""),
                tool_args.get("text", ""),
                expect=tool_args.get("expect"),
                name=tool_args.get("name"),
            )
        elif tool_name == "paste_text":
            return self._do_paste_text(
                tool_args.get("text", ""),
                expect=tool_args.get("expect"),
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
            reject = self._gate_mark_step_done(
                tool_args.get("reason", ""), tool_args.get("evidence", "")
            )
            if reject is not None:
                return reject
            return {
                "__step_complete__": True,
                "success": True,
                "reason": tool_args.get("reason", ""),
                "evidence": tool_args.get("evidence", ""),
                "unverified_done": getattr(self, "_done_attempts", 0) >= 2
                and (self._strong_evidence() is None
                     or not (self._strong_evidence().get("state_changed")
                             or self._strong_evidence().get("verified"))),
            }
        elif tool_name == "mark_step_failed":
            reject = self._gate_mark_step_failed(tool_args.get("reason", ""))
            if reject is not None:
                return reject
            return {"__step_failed__": True, "reason": tool_args.get("reason", "")}
        elif tool_name == "report_infeasible":
            return {
                "__step_infeasible__": True,
                "reason": tool_args.get("reason", ""),
                "tried": tool_args.get("tried", ""),
            }
        elif tool_name == "ask_user":
            return {
                "__ask_user__": True,
                "question": tool_args.get("question", ""),
            }
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
        on_tool_event: Optional[callable] = None,
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
        self._step_tel = et.new_step_telemetry()  # T1 遥测（engine 步末读取）
        loop_detector = _LoopDetector(
            self._step_tel["loop_events"]
        )  # 0.4 卡死检测（每步独立，越界事件直接写入遥测）
        self._reset_step_ledger()  # 0.7 证据账本（每步独立）
        step.terminal_kind = None
        step.user_question = None
        step.evidence = None

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

            # On subsequent rounds, nudge the LLM to continue.
            # 0.4: 若检测到重复动作/观测停滞/级联失败，改写为分级纠偏 nudge。
            if round_num > 0:
                corrective = loop_detector.build_nudge()
                messages.append(
                    {
                        "role": "user",
                        "content": corrective
                        or "继续。你还可以调用工具。每次只调用一个工具。",
                    }
                )
                # R2：原 time.sleep(1.5) "throttle OmniParser load" 为已退役组件的
                # 化石节流（OmniParser 已下线），50 轮一步纯睡 ~73s，删除。
                # LLM 限流由 API 层重试/退避处理，不在此处。

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
            t0 = time.perf_counter()
            if on_tool_event:
                try:
                    on_tool_event(
                        "tool_called",
                        {"tool": tool_name, "args": tool_args or {}},
                    )
                except Exception:
                    pass
            result = self.dispatch_tool(tool_name, tool_args)
            if result is None:
                result = {"success": False, "error": "tool dispatch returned None"}
            # 0.4 卡死检测记账：动作哈希滑窗 + 观测指纹（观察类工具记录界面状态）
            loop_detector.record_action(
                tool_name, tool_args or {}, bool(result.get("success"))
            )
            if tool_name == "get_screen_info" and isinstance(result, dict):
                loop_detector.record_observation(result.get("elements"))
            duration_ms = int((time.perf_counter() - t0) * 1000)
            # T1 遥测：本次工具调用记入步遥测
            et.tally_tool(self._step_tel, tool_name, result, duration_ms)
            if on_tool_event and result:
                try:
                    on_tool_event(
                        "tool_result",
                        {
                            "tool": tool_name,
                            "success": bool(result.get("success")),
                            "action_summary": result.get("action_summary"),
                            "duration_ms": duration_ms,
                            "error": result.get("error"),
                            "error_code": result.get("error_code"),
                            "hint": result.get("hint"),
                        },
                    )
                except Exception:
                    pass
            logger.info(
                f"Round {round_num}: {tool_name}({tool_args}) → success={result.get('success') if result else 'N/A'}"
            )

            # If the tool took a screenshot, push it to the frontend
            if tool_name == "get_screen_info" and on_screenshot and result:
                annotated = result.get("annotated_image")
                if annotated:
                    try:
                        on_screenshot(annotated)
                    except Exception:
                        pass
            # R1：截图 base64 只供 B 端渲染（SSE），绝不进 LLM 上下文——
            # deepseek-chat 是纯文本模型，这串 base64 是每次数万 token 的纯噪声。
            if isinstance(result, dict):
                result.pop("annotated_image", None)

            # Check for step completion signals
            if result and result.get("__step_complete__"):
                step.status = "done"
                step.action_summary = action_summary or result.get(
                    "reason", "step completed"
                )
                # 0.7：done 必须带可核查证据（gate 已在 dispatch 层把关）
                strong = self._strong_evidence()
                ev_text = (result.get("evidence") or "").strip()
                if strong is not None:
                    auto_ev = (
                        f"{strong['tool']}→{strong['target']}"
                        f" state_changed={strong.get('state_changed')}"
                        f" verified={strong.get('verified')}"
                    )
                    step.evidence = f"{auto_ev}; {ev_text}".strip("; ")
                else:
                    step.evidence = ev_text
                if result.get("unverified_done"):
                    step.evidence = (step.evidence or "") + " [unverified_done]"
                    step.action_summary = (step.action_summary or "") + "（未独立验证）"
                return step
            if result and result.get("__step_failed__"):
                step.status = "failed"
                step.action_summary = result.get("reason", "step failed")
                return step
            if result and result.get("__step_infeasible__"):
                step.status = "failed"
                step.terminal_kind = "infeasible"
                step.action_summary = (
                    f"[不可行] {result.get('reason', '')}"
                    + (f"｜已尝试: {result.get('tried')}" if result.get("tried") else "")
                )
                return step
            if result and result.get("__ask_user__"):
                step.status = "failed"
                step.terminal_kind = "ask_user"
                step.user_question = result.get("question", "")
                step.action_summary = f"[需用户决策] {result.get('question', '')}"
                return step

            # Accumulate action_summary from tool returns
            if result and result.get("action_summary"):
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
                    "content": json.dumps(_strip_for_llm(result), ensure_ascii=False),
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
            # T1 遥测：采集 token 用量（此前 data["usage"] 一直被丢弃）
            et.tally_llm_usage(getattr(self, "_step_tel", None), data.get("usage") or {})
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
