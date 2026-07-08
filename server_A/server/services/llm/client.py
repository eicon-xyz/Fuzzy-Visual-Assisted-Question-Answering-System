"""
LLM 客户端 — 支持多模态（SiliconCloud Qwen3.6 等）和纯文本（DeepSeek）
"""

import json
import re
from typing import List, Optional

import httpx

from server.config import settings
from server.models.schemas import UIElement
from server.services.llm.prompt import SYSTEM_PROMPT
from server.services.perception import serialize_elements


def _get_api_config():
    """获取当前 LLM API 配置，优先使用 LLM_* 变量，fallback 到 DEEPSEEK_*"""
    api_key = settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY
    base_url = settings.LLM_BASE_URL or settings.DEEPSEEK_BASE_URL
    model = settings.LLM_MODEL or settings.DEEPSEEK_MODEL
    return api_key, base_url, model


def _strip_data_uri_prefix(image: str) -> str:
    """去掉 data URI 前缀，返回纯 base64 字符串。"""
    if "," in image and image.startswith("data:"):
        return image.split(",", 1)[1]
    return image


def _build_user_message(query: str, image_base64: Optional[str] = None) -> dict:
    """
    构建 user message。
    有图时使用 OpenAI Vision 格式（content 数组含 image_url 块）；
    无图时使用纯文本格式。

    NOTE: image_base64 is expected to be pre-compressed to ≤1024px by
    omniparser_client._compress_som_image(). If it arrives uncompressed,
    we pass it as-is to avoid blocking the LLM call path.
    """
    if not image_base64:
        return {"role": "user", "content": query}

    # If already JPEG (from compress), use as-is; if PNG, pass through
    raw_b64 = _strip_data_uri_prefix(image_base64)
    mime = "image/jpeg" if image_base64.startswith("data:image/jpeg") else "image/png"
    return {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{raw_b64}"},
            },
            {"type": "text", "text": query},
        ],
    }


def call_deepseek(
    query: str,
    elements: Optional[List[UIElement]] = None,
    timeout: int = 60,
    image_base64: Optional[str] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> Optional[dict]:
    """
    调用 LLM API 生成操作步骤与约束条件。
    支持多模态（看图规划）和纯文本两种模式。

    Args:
        query: 用户原始查询
        elements: 当前屏幕 UI 元素列表
        timeout: HTTP 超时时间
        image_base64: SoM 标注图的 base64（可选）
        system_prompt: 自定义 system prompt（为 None 时使用默认步骤规划 prompt）
        temperature: 温度参数
        max_tokens: 最大输出 token 数

    Returns:
        包含 steps 与 constraints 的字典，失败返回 None
    """
    api_key, base_url, model = _get_api_config()
    if not api_key:
        return None

    element_text = serialize_elements(elements) if elements else "（未检测到 UI 元素）"
    if system_prompt is not None:
        prompt = (
            system_prompt.format(element_list=element_text)
            if "{element_list}" in system_prompt
            else system_prompt
        )
    else:
        prompt = SYSTEM_PROMPT.format(element_list=element_text)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        _build_user_message(query, image_base64),
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return parse_json_response(content)
    except Exception as e:
        print(f"[LLM Error] {type(e).__name__}: {e}")
        return None


def parse_json_response(content: str) -> Optional[dict]:
    """从 LLM 返回内容中提取任意 JSON 对象（不限键名）。"""
    if not content:
        return None
    content = content.strip()
    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # 尝试从 markdown 代码块中提取
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试查找第一个 JSON 对象
    json_match = re.search(r"\{[\s\S]*\}", content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def parse_llm_response(content: str) -> Optional[dict]:
    """从 LLM 返回内容中提取完整 JSON（含 steps 与 constraints）"""
    data = parse_json_response(content)
    if data and "steps" in data:
        return data
    return None


def parse_llm_steps(content: str) -> Optional[List[dict]]:
    """从 LLM 返回内容中提取步骤 JSON（兼容旧接口）"""
    response = parse_llm_response(content)
    if response is not None:
        return response.get("steps")
    return None
