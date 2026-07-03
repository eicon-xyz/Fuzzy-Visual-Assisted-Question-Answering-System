"""
LLM 客户端 — 多 Provider 支持（DeepSeek / OpenAI / Claude / OpenRouter / Ollama）
v1.1.0: 从单一 DeepSeek 扩展为多 Provider + fallback 链
"""
import json
import os
import re
from typing import List, Optional

import httpx

from server_v2.config import settings
from server_v2.models.schemas import UIElement
from server_v2.services.perception import serialize_elements
from server_v2.services.llm.prompt import SYSTEM_PROMPT


def _get_api_config():
    """获取当前 LLM API 配置，优先 LLM_* 变量，fallback 到 DEEPSEEK_*（向后兼容）"""
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
    api_key = settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY
    base_url = settings.LLM_BASE_URL or settings.DEEPSEEK_BASE_URL
    model = settings.LLM_MODEL or settings.DEEPSEEK_MODEL

    # 按 provider 覆盖
    if provider == "openai":
        api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
    elif provider == "claude":
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        base_url = base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    elif provider == "openrouter":
        api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        base_url = base_url or "https://openrouter.ai/api/v1"
        model = model or os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
    elif provider == "ollama":
        api_key = "ollama"
        base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        model = model or os.getenv("OLLAMA_MODEL", "llama3.2")

    return provider, api_key, base_url, model


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
    """
    if not image_base64:
        return {"role": "user", "content": query}

    raw_b64 = _strip_data_uri_prefix(image_base64)
    return {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{raw_b64}"},
            },
            {"type": "text", "text": query},
        ],
    }


def call_deepseek(
    query: str,
    elements: Optional[List[UIElement]] = None,
    timeout: int = 30,
    image_base64: Optional[str] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> Optional[dict]:
    """
    调用 LLM API 生成操作步骤与约束条件（向后兼容别名）。
    实际委托给 call_llm()。
    """
    return call_llm(
        query=query,
        elements=elements,
        timeout=timeout,
        image_base64=image_base64,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def call_llm(
    query: str,
    elements: Optional[List[UIElement]] = None,
    timeout: int = 30,
    image_base64: Optional[str] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> Optional[dict]:
    """
    调用 LLM API 生成操作步骤与约束条件。
    支持多 Provider（DeepSeek/OpenAI/Claude/OpenRouter/Ollama）。
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
    provider, api_key, base_url, model = _get_api_config()
    if not api_key:
        return None

    element_text = serialize_elements(elements) if elements else "（未检测到 UI 元素）"
    if system_prompt is not None:
        prompt = system_prompt.format(element_list=element_text) if "{element_list}" in system_prompt else system_prompt
    else:
        prompt = SYSTEM_PROMPT.format(element_list=element_text)

    try:
        # Claude 使用不同的 API 格式（Messages API）
        if provider == "claude":
            return _call_claude(
                query=query, prompt=prompt, base_url=base_url, api_key=api_key,
                model=model, image_base64=image_base64,
                temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            )

        # Ollama 使用不同的 API 格式
        if provider == "ollama":
            return _call_ollama(
                query=query, prompt=prompt, base_url=base_url,
                model=model, image_base64=image_base64,
                temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            )

        # OpenAI 兼容格式（DeepSeek / OpenAI / OpenRouter / Groq 等）
        extra_headers = {}
        if provider == "openrouter":
            extra_headers["HTTP-Referer"] = "https://hajimi.local"
            extra_headers["X-Title"] = "HAJIMI"

        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    **extra_headers,
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
        print(f"[LLM Error] provider={provider} model={model} {type(e).__name__}: {e}")
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


# ────────────────────────── Provider 特定实现 ──────────────────────────


def _call_claude(query: str, prompt: str, base_url: str, api_key: str,
                 model: str, image_base64: Optional[str],
                 temperature: float, max_tokens: int, timeout: int) -> Optional[dict]:
    """Claude Messages API（非 OpenAI 兼容格式）"""
    messages = _build_claude_messages(query, image_base64)

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": prompt,
                "messages": messages,
            },
        )
        response.raise_for_status()
        data = response.json()
        # Claude 返回 content[0].text
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        return parse_json_response(content)


def _build_claude_messages(query: str, image_base64: Optional[str]) -> list:
    """构建 Claude Messages API 格式的 user message"""
    if not image_base64:
        return [{"role": "user", "content": query}]

    raw_b64 = _strip_data_uri_prefix(image_base64)
    return [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": raw_b64,
                },
            },
            {"type": "text", "text": query},
        ],
    }]


def _call_ollama(query: str, prompt: str, base_url: str,
                 model: str, image_base64: Optional[str],
                 temperature: float, max_tokens: int, timeout: int) -> Optional[dict]:
    """Ollama API（/api/chat 格式）"""
    messages = [{"role": "system", "content": prompt}]
    user_msg = {"role": "user", "content": query}
    if image_base64:
        raw_b64 = _strip_data_uri_prefix(image_base64)
        user_msg["images"] = [raw_b64]
    messages.append(user_msg)

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url}/api/chat",
            headers={"Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        return parse_json_response(content)
