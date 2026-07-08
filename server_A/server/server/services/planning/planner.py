"""
Planning Agent — text-only LLM call that decomposes a user query
into atomic operation steps. No screenshots, no OmniParser.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from server.models.schemas import PlanningStep
from server.services.llm.providers import call_llm, extract_json_object

logger = logging.getLogger(__name__)

PLANNING_SYSTEM_PROMPT = """你是桌面操作规划专家。将用户的自然语言指令分解为原子操作步骤。

## 步骤粒度原则
- 一个步骤对应一个用户可感知的界面状态变化
- "输入文字 + 按回车搜索" 可合并为一步（如"在搜索框中搜索'xxx'"）
- "打开应用" 必须独立一步（涉及等待加载和上下文切换）
- 不要为隐含操作生成独立步骤（"等待加载"由执行Agent自行处理，你不需要写）

## 规则
1. 每个步骤只做一件用户可感知的事
2. 保留用户原始指令中的所有信息（应用名、搜索词、文件名等）
3. 按操作的自然顺序排列步骤
4. 步骤只描述"要达成什么目标"，不描述"如何操作"
5. 如果指令涉及特定应用，第一步必须是打开该应用

## 输出格式
输出纯JSON（无markdown代码块标记）：
{"goal": "一句话概括任务目标", "steps": [{"step_index": 1, "instruction": "..."}, ...]}

## 示例
输入："打开微信，给张三发'明天见'"
输出：{"goal": "打开微信并给张三发消息", "steps": [{"step_index": 1, "instruction": "打开微信应用"}, {"step_index": 2, "instruction": "找到张三的聊天并发送消息'明天见'"}]}

输入："打开浏览器，搜索天气"
输出：{"goal": "打开浏览器搜索天气", "steps": [{"step_index": 1, "instruction": "打开浏览器应用"}, {"step_index": 2, "instruction": "在搜索框中搜索'天气'"}]}"""


@dataclass
class PlanningResult:
    goal: str
    steps: List[PlanningStep] = field(default_factory=list)


def plan_steps(query: str, max_retries: int = 2) -> PlanningResult:
    """Decompose a user query into atomic steps using Planning Agent LLM.

    Args:
        query: Natural language user instruction
        max_retries: Max retries on JSON parse failure (default 2 = 3 total attempts)

    Returns:
        PlanningResult with goal string and list of PlanningStep

    Raises:
        ValueError: if Planning Agent fails after all retries
    """
    user_text = f"用户指令：「{query}」\n\n请将这条指令分解为操作步骤。只输出JSON。"

    for attempt in range(max_retries + 1):
        try:
            raw = call_llm(
                user_text=user_text,
                system_prompt=PLANNING_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=1024,
                timeout=60,
            )
            data = extract_json_object(raw)

            goal = data.get("goal", query)
            raw_steps = data.get("steps", [])
            if not raw_steps:
                # Fallback: single step = the whole query
                raw_steps = [{"step_index": 1, "instruction": query}]

            steps = []
            for s in raw_steps:
                if isinstance(s, str):
                    steps.append(
                        PlanningStep(
                            step_index=len(steps) + 1,
                            instruction=s,
                        )
                    )
                elif isinstance(s, dict):
                    steps.append(
                        PlanningStep(
                            step_index=s.get("step_index", len(steps) + 1),
                            instruction=s.get("instruction", str(s)),
                        )
                    )

            if not steps:
                raise ValueError("Planning Agent returned empty steps")

            logger.info(f"Planning: {goal} ({len(steps)} steps)")
            return PlanningResult(goal=goal, steps=steps)

        except Exception as e:
            logger.warning(
                f"Planning Agent attempt {attempt+1}/{max_retries+1} failed: {e}"
            )
            if attempt >= max_retries:
                raise ValueError(
                    f"Planning Agent failed after {max_retries+1} attempts: {e}"
                ) from e
            continue

    # Unreachable but type-checker safe
    raise ValueError("Planning Agent failed")
