"""OpenAI Chat Completions vs Responses API 统一调用（daseinai 等中转需 responses）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import httpx

from server.config import reload_settings, settings


def resolve_wire_api(base_url: str) -> str:
    """返回 chat | responses。"""
    reload_settings()
    explicit = (getattr(settings, "LLM_WIRE_API", None) or "").strip().lower()
    if explicit in ("chat", "responses"):
        return explicit
    host = (base_url or "").lower()
    if "daseinai" in host:
        return "responses"
    return "chat"


def _collect_text_fragments(value: Any, parts: list[str]) -> None:
    """递归收集 JSON 中所有字符串叶子，用于 reasoning / 嵌套 content。"""
    if value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            parts.append(text)
        return
    if isinstance(value, dict):
        for key in (
            "text",
            "output_text",
            "content",
            "summary",
            "value",
            "message",
        ):
            if key in value:
                _collect_text_fragments(value[key], parts)
        for key, nested in value.items():
            if key in ("text", "output_text", "content", "summary", "value", "message"):
                continue
            if isinstance(nested, (dict, list)):
                _collect_text_fragments(nested, parts)
        return
    if isinstance(value, list):
        for item in value:
            _collect_text_fragments(item, parts)


def extract_responses_text(data: dict) -> str:
    """从 Responses API JSON 提取全部文本（含 reasoning 块），供 [POINT] 解析。"""
    if not isinstance(data, dict):
        return ""

    if data.get("output_text"):
        return str(data["output_text"])

    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type") or ""
        if item_type == "message":
            _collect_text_fragments(item.get("content"), parts)
        elif item_type in ("output_text", "text"):
            _collect_text_fragments(item.get("text") or item.get("output_text"), parts)
        elif item_type == "reasoning":
            _collect_text_fragments(
                item.get("summary") or item.get("content") or item,
                parts,
            )
        else:
            _collect_text_fragments(item, parts)

    if parts:
        return "\n".join(parts)

    _collect_text_fragments(data, parts)
    return "\n".join(parts)


def _build_chat_messages(
    system: str,
    user: str,
    *,
    image_b64: Optional[str] = None,
    vision: bool = False,
) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": system}]
    if vision and image_b64:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": user})
    return messages


def _build_responses_input(
    system: str,
    user: str,
    *,
    image_b64: Optional[str] = None,
    vision: bool = False,
) -> list[dict]:
    user_content: Any
    if vision and image_b64:
        user_content = [
            {"type": "input_text", "text": user},
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{image_b64}",
            },
        ]
    else:
        user_content = user
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


def post_llm(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    image_b64: Optional[str] = None,
    vision: bool = False,
    max_tokens: int,
    timeout: float,
    wire_api: Optional[str] = None,
) -> Tuple[str, dict]:
    """调用 LLM，返回 (text, usage_meta)。"""
    base = (base_url or "").rstrip("/")
    if not api_key or not base:
        raise RuntimeError("LLM: API key or base URL not configured")

    wire = (wire_api or resolve_wire_api(base)).lower()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=timeout) as client:
        if wire == "responses":
            payload: Dict[str, Any] = {
                "model": model,
                "input": _build_responses_input(
                    system, user, image_b64=image_b64, vision=vision
                ),
                "max_output_tokens": max_tokens,
            }
            resp = client.post(f"{base}/responses", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = extract_responses_text(data)
            usage = data.get("usage") or {}
            return content, usage

        payload = {
            "model": model,
            "messages": _build_chat_messages(
                system, user, image_b64=image_b64, vision=vision
            ),
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        resp = client.post(f"{base}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"] or ""
        return content, data.get("usage") or {}
