"""
Plan steps without OmniParser — text/vision LLM only (OpenGuider-style planner).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from server.services.llm.client import call_deepseek

PLANNER_SYSTEM = """你是桌面操作指引助手。根据用户目标制定分步计划。
不要依赖 UI 元素编号；每步应可被用户独立验证。
严格返回 JSON，不要 markdown 代码块：
{
  "steps": [
    {
      "action": "简短动作",
      "description": "面向用户的单步说明",
      "target_element_id": "",
      "interaction": "screen"
    }
  ],
  "constraints": null
}
规则：
1. 每步只做一件事；keyboard 类步骤 interaction 设为 "keyboard"。
2. 不要编造 element_id；留空字符串。
3. 步骤数量 2-6 步为宜。"""


def plan_without_parse(
    query: str,
    *,
    image_base64: Optional[str] = None,
    use_vision_hint: bool = False,
) -> Tuple[List[dict], Optional[dict], dict]:
    """
    Generate steps without OmniParser element list.

    Returns:
        (raw_steps, constraints, llm_meta)
    """
    llm_meta: dict = {
        "llm_called": True,
        "parse_skipped": True,
        "plan_only": True,
    }
    prompt = PLANNER_SYSTEM
    vision_image = image_base64 if use_vision_hint and image_base64 else None
    speed = "precision" if vision_image else "fast"
    parsed, err, latency, provider, used_vision = call_deepseek(
        query,
        elements=None,
        image_base64=vision_image,
        system_prompt=prompt,
        temperature=0.2,
        max_tokens=900,
        speed_mode=speed,
    )
    llm_meta["llm_latency_ms"] = latency
    llm_meta["llm_provider"] = provider
    llm_meta["llm_used_vision"] = used_vision
    if err:
        llm_meta["llm_error"] = err
    if parsed and parsed.get("steps"):
        return parsed["steps"], parsed.get("constraints"), llm_meta
    return (
        [
            {
                "action": "按指引操作",
                "description": query,
                "target_element_id": "",
                "interaction": "screen",
            }
        ],
        None,
        llm_meta,
    )
