"""L4 Planner：默认纯文本 + screen_hints，可选 Vision。"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from server.services.l4.config import get_l4_settings
from server.services.l4.llm_client import call_l4_llm, parse_json_steps
from server.services.l4.pipeline import run_pre_pipeline
from server.services.l4.types import L4ScreenContext

logger = logging.getLogger(__name__)

PLANNER_SYSTEM = """你是桌面 GUI 自动化助手。根据用户任务生成可执行步骤计划。
输出必须是 JSON 数组，每项包含:
  - step_number (int)
  - action (click|type|scroll|wait|hotkey|open_app|...)
  - target (string, 简短描述 UI 元素)
  - description (string, 用户可读说明)
  - value (optional, 输入文本或参数)

不要输出坐标；定位由后续 Locator 完成。
wait、hotkey、open_app、切换窗口、等待加载等步骤不需要屏幕坐标，请使用对应 action。
click 等需点击 UI 的步骤，target 应描述当前截图中可见的元素。
若用户仅要求「指示/找到/标出/在哪」某元素且已提供截图：默认生成 1 个 click 步，不要添加「等待桌面加载」等 wait 步。
单目标指示任务优先 1 步；target 使用截图中可见名称（如「回收站」「Dev-C++」）。
用户意图为「打开 XX 浏览器/应用并操作」且截图为桌面时：优先 open_app（value 如 chrome）或 Win 搜索，不要默认拆成「点击桌面图标」。
仅当用户明确要求「指出/找到/标出桌面图标在哪」时才生成 click 桌面图标步。
仅输出 JSON，无 markdown 包裹。"""


def plan_l4_steps(
    user_query: str,
    *,
    image_b64: Optional[str] = None,
    screen_ctx: Optional[L4ScreenContext] = None,
    constraints: Optional[dict] = None,
) -> tuple[List[dict], Dict[str, Any]]:
    cfg = get_l4_settings()
    ctx = screen_ctx or L4ScreenContext()
    ctx = run_pre_pipeline(ctx, enabled=cfg.pipeline_enabled and cfg.screen_hints)

    user_parts = [f"任务: {user_query}"]
    if ctx.screen_hints:
        user_parts.append(f"屏幕上下文:\n{ctx.screen_hints}")
    if constraints:
        user_parts.append(f"约束: {json.dumps(constraints, ensure_ascii=False)}")

    use_vision = cfg.planner_use_vision and bool(image_b64)
    raw, meta = call_l4_llm(
        role="planner",
        system=PLANNER_SYSTEM,
        user="\n\n".join(user_parts),
        image_b64=image_b64 if use_vision else None,
        vision=use_vision,
    )
    steps = parse_json_steps(raw)
    meta["planner_use_vision"] = use_vision
    meta["screen_hints"] = ctx.screen_hints
    logger.info("L4 planner produced %d steps", len(steps))
    return steps, meta
