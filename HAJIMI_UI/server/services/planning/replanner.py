"""
动态重规划服务（P2 核心实现区）
当激活步骤无 target_element_id 时，基于新截图重新解析并补全绑定
"""
from typing import List, Optional

from server.models.schemas import Step, UIElement
from server.services.perception import serialize_elements
from server.services.planning.annotation import build_annotation


REPLAN_PROMPT = """你是一个桌面操作指引助手。当前用户正在执行一个多步骤任务，现在需要为后续未绑定界面元素的步骤补充目标元素。

## 用户的原始请求
{original_query}

## 当前屏幕 UI 元素
{element_list}

## 尚未绑定元素的后续步骤
{upcoming_steps}

## 输出格式
严格按以下 JSON 格式返回，不要 markdown 代码块。必须保留每条步骤的 step_index，只修改 target_element_id，保持 action 和 description 不变：
{{
  "steps": [
    {{"step_index": 2, "action": "...", "description": "...", "target_element_id": "~1"}},
    {{"step_index": 3, "action": "...", "description": "...", "target_element_id": ""}}
  ]
}}

## 要求
1. 对于"当前屏幕 UI 元素"中明显可匹配到元素的步骤，补全 `target_element_id`。
2. 若某一步在当前屏幕仍无匹配元素（如下一步会打开新窗口/弹窗），`target_element_id` 保持为空字符串 `""`。
3. 只需返回需要更新的步骤；未返回的步骤保持原状。
"""


def _serialize_steps_for_replan(steps: List[Step]) -> str:
    """将未绑定步骤序列化为 LLM 可读文本"""
    lines = []
    for s in steps:
        lines.append(
            f"  Step {s.step_index}: [{s.action}] {s.description} → current_target={s.target_element_id or '(空)'}"
        )
    return "\n".join(lines)





def _call_replan_llm(prompt: str, timeout: int = 30) -> Optional[List[dict]]:
    """调用 LLM 进行重规划"""
    from server.services.llm.client import call_deepseek

    result = call_deepseek(
        query="请为上述步骤补全 target_element_id。",
        system_prompt=prompt,
        temperature=0.2,
        max_tokens=2000,
        timeout=timeout,
    )
    if result and "steps" in result:
        return result["steps"]
    return None


def replan_steps(
    original_query: str,
    current_step_index: int,
    all_steps: List[Step],
    new_elements: List[UIElement],
) -> List[Step]:
    """
    基于新截图的元素列表，为未绑定步骤填充 target_element_id

    Args:
        original_query: 用户原始请求
        current_step_index: 当前步骤索引（0-based）
        all_steps: 全部步骤列表
        new_elements: 新截图解析出的 UI 元素

    Returns:
        更新后的步骤列表
    """
    unbound_steps = [
        s for s in all_steps[current_step_index:] if not s.target_element_id
    ]

    if not unbound_steps or not new_elements:
        return list(all_steps)

    element_text = serialize_elements(new_elements)
    upcoming_text = _serialize_steps_for_replan(unbound_steps)

    prompt = REPLAN_PROMPT.format(
        original_query=original_query,
        element_list=element_text,
        upcoming_steps=upcoming_text,
    )

    replanned = _call_replan_llm(prompt)

    if not replanned:
        return list(all_steps)

    element_by_id = {e.element_id: e for e in new_elements}
    updated_steps = list(all_steps)

    # 用于 LLM 未返回 step_index 时的顺序回退匹配
    unbound_index = 0

    for raw in replanned:
        step_index = raw.get("step_index")
        target_id = raw.get("target_element_id", "")

        if step_index is not None:
            idx = step_index - 1
            if 0 <= idx < len(updated_steps):
                element = element_by_id.get(target_id) if target_id else None
                if element:
                    updated_steps[idx].target_element_id = target_id
                    updated_steps[idx].annotation = build_annotation(
                        element,
                        annotation_type="highlight_only",
                        label_text=target_id,
                    )
                else:
                    updated_steps[idx].target_element_id = None
                    updated_steps[idx].annotation = None
        else:
            # 按顺序匹配到下一个未绑定步骤
            while unbound_index < len(unbound_steps):
                unbound_step = unbound_steps[unbound_index]
                unbound_index += 1
                idx = unbound_step.step_index - 1
                if 0 <= idx < len(updated_steps):
                    element = element_by_id.get(target_id) if target_id else None
                    if element:
                        updated_steps[idx].target_element_id = target_id
                        updated_steps[idx].annotation = build_annotation(
                            element,
                            annotation_type="highlight_only",
                            label_text=target_id,
                        )
                    else:
                        updated_steps[idx].target_element_id = None
                        updated_steps[idx].annotation = None
                    break

    return updated_steps
