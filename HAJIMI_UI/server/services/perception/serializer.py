"""
UI 元素序列化器
将 OmniParser 输出的 UI 元素列表转换为 LLM prompt 文本
"""
from typing import List

from server.models.schemas import UIElement


def serialize_elements(elements: List[UIElement], max_count: int = 25) -> str:
    """
    将 UI 元素列表序列化为 LLM prompt 文本

    Args:
        elements: OmniParser 输出的 UI 元素列表
        max_count: 最多输出多少个元素，控制 token 消耗

    Returns:
        格式化后的元素描述文本
    """
    if not elements:
        return "（未检测到 UI 元素）"

    sorted_els = sorted(elements, key=lambda e: e.confidence, reverse=True)[:max_count]
    lines = []
    for e in sorted_els:
        text = e.text.strip() if e.text else "(无文本)"
        lines.append(
            f"  {e.element_id}: {e.element_type} \"{text}\" (置信度:{e.confidence:.2f})"
        )
    return "\n".join(lines)
