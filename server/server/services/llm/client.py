"""
DeepSeek LLM 客户端
"""
import json
import re
from typing import List, Optional

import httpx

from server.config import settings
from server.models.schemas import UIElement
from server.services.perception import serialize_elements
from server.services.llm.prompt import SYSTEM_PROMPT


def call_deepseek(
    query: str,
    elements: Optional[List[UIElement]] = None,
    timeout: int = 30,
) -> Optional[dict]:
    """
    调用 DeepSeek API 生成操作步骤与约束条件

    Args:
        query: 用户原始查询
        elements: 当前屏幕 UI 元素列表（P0 新增）
        timeout: HTTP 超时时间

    Returns:
        包含 steps 与 constraints 的字典，失败返回 None
    """
    if not settings.DEEPSEEK_API_KEY:
        return None

    element_text = serialize_elements(elements) if elements else "（未检测到 UI 元素）"
    prompt = SYSTEM_PROMPT.format(element_list=element_text)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return parse_llm_response(content)
    except Exception as e:
        print(f"[LLM Error] {type(e).__name__}: {e}")
        return None


def parse_llm_response(content: str) -> Optional[dict]:
    """从 LLM 返回内容中提取完整 JSON（含 steps 与 constraints）"""
    # 尝试直接解析
    try:
        data = json.loads(content)
        if "steps" in data:
            return data
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if code_block:
        try:
            data = json.loads(code_block.group(1))
            if "steps" in data:
                return data
        except json.JSONDecodeError:
            pass

    # 尝试查找第一个 JSON 对象
    json_match = re.search(r"\{[\s\S]*\"steps\"[\s\S]*\}", content)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if "steps" in data:
                return data
        except json.JSONDecodeError:
            pass

    return None


def parse_llm_steps(content: str) -> Optional[List[dict]]:
    """从 LLM 返回内容中提取步骤 JSON（兼容旧接口）"""
    response = parse_llm_response(content)
    if response is not None:
        return response.get("steps")
    return None
