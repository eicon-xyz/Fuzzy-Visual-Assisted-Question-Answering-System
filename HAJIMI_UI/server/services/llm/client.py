"""
LLM 客户端 — 速度模式 fast/balanced/precision + 多提供商 fallback
"""

import base64
import io
import json
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import httpx

from server.config import reload_settings, settings
from server.models.schemas import UIElement
from server.services.perception import serialize_elements
from server.services.llm.prompt import FAST_SYSTEM_PROMPT, SYSTEM_PROMPT


@dataclass(frozen=True)
class LlmProvider:
    name: str
    api_key: str
    base_url: str
    model: str
    timeout: float
    vision: bool = False


def _get_api_config():
    reload_settings()
    api_key = settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY
    base_url = settings.LLM_BASE_URL or settings.DEEPSEEK_BASE_URL
    model = settings.LLM_MODEL or settings.DEEPSEEK_MODEL
    return api_key, base_url, model


def _resolve_speed_mode(speed_mode: Optional[str] = None) -> str:
    reload_settings()
    mode = (speed_mode or settings.LLM_SPEED_MODE or "fast").lower()
    if mode not in ("fast", "balanced", "precision"):
        return "fast"
    return mode


def _llm_provider_chain(*, speed_mode: Optional[str] = None) -> List[LlmProvider]:
    reload_settings()
    mode = _resolve_speed_mode(speed_mode)
    text_timeout = float(settings.LLM_ATTEMPT_TIMEOUT or 15)
    vision_timeout = float(settings.LLM_VISION_ATTEMPT_TIMEOUT or 45)
    fast_timeout = float(settings.LLM_FAST_TIMEOUT or 15)
    chain: List[LlmProvider] = []

    ds_key = settings.DEEPSEEK_API_KEY
    ds_url = settings.DEEPSEEK_BASE_URL or "https://api.deepseek.com"
    ds_model = settings.DEEPSEEK_MODEL or "deepseek-chat"
    pk = settings.LLM_API_KEY
    pu = settings.LLM_BASE_URL
    pm = settings.LLM_MODEL

    if mode == "fast":
        if ds_key:
            chain.append(
                LlmProvider("deepseek", ds_key, ds_url, ds_model, fast_timeout, False)
            )
        elif pk and pu and pm:
            chain.append(
                LlmProvider("primary", pk, pu, pm, fast_timeout, False)
            )
    elif mode == "balanced":
        if ds_key:
            chain.append(
                LlmProvider("deepseek", ds_key, ds_url, ds_model, fast_timeout, False)
            )
        if pk and pu and pm:
            chain.append(
                LlmProvider("primary", pk, pu, pm, text_timeout, False)
            )
    else:
        if pk and pu and pm:
            chain.append(
                LlmProvider("primary", pk, pu, pm, vision_timeout, True)
            )
        if ds_key:
            chain.append(
                LlmProvider("deepseek", ds_key, ds_url, ds_model, text_timeout, False)
            )

    return chain


def _httpx_timeout(total: float) -> httpx.Timeout:
    """Separate connect/read limits so hung TCP cannot block past read budget."""
    connect = min(5.0, total)
    return httpx.Timeout(connect=connect, read=total, write=min(30.0, total), pool=5.0)


def _llm_provider_chain_fast_fallback(
    *, speed_mode: Optional[str] = None
) -> List[LlmProvider]:
    """fast 模式：DeepSeek 超时/失败后追加主模型纯文本 fallback。"""
    chain = _llm_provider_chain(speed_mode="fast")
    if _resolve_speed_mode(speed_mode) != "fast":
        return chain
    reload_settings()
    text_timeout = float(settings.LLM_ATTEMPT_TIMEOUT or 15)
    pk = settings.LLM_API_KEY
    pu = settings.LLM_BASE_URL
    pm = settings.LLM_MODEL
    if pk and pu and pm:
        names = {p.name for p in chain}
        if "primary" not in names:
            chain.append(
                LlmProvider("primary", pk, pu, pm, text_timeout, False)
            )
    return chain


def _strip_data_uri_prefix(image: str) -> str:
    if "," in image and image.startswith("data:"):
        return image.split(",", 1)[1]
    return image


def _maybe_downscale_for_llm(image_base64: str, max_side: int = 768) -> str:
    raw_b64 = _strip_data_uri_prefix(image_base64)
    try:
        from PIL import Image

        raw = base64.b64decode(raw_b64)
        with Image.open(io.BytesIO(raw)) as img:
            w, h = img.width, img.height
            longest = max(w, h)
            if longest <= max_side:
                return raw_b64
            ratio = max_side / longest
            new_w, new_h = int(w * ratio), int(h * ratio)
            work = img.convert("RGB") if img.mode != "RGB" else img.copy()
            work = work.resize((new_w, new_h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            work.save(buf, format="PNG")
            print(
                f"[LLM] downscale vision image {w}x{h} -> {new_w}x{new_h} max_side={max_side}"
            )
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:
        print(f"[LLM] vision downscale skipped: {exc}")
        return raw_b64


def _build_user_message(
    query: str, image_base64: Optional[str] = None, *, allow_vision: bool = True
) -> dict:
    if not image_base64 or not allow_vision:
        return {"role": "user", "content": query}

    raw_b64 = _maybe_downscale_for_llm(image_base64)
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


def _call_provider_once(
    provider: LlmProvider,
    *,
    prompt: str,
    query: str,
    image_base64: Optional[str],
    temperature: float,
    max_tokens: int,
) -> Tuple[Optional[dict], Optional[str], int, bool]:
    use_image = image_base64 if provider.vision else None
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=_httpx_timeout(provider.timeout)) as client:
            response = client.post(
                f"{provider.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": provider.model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        _build_user_message(
                            query, use_image, allow_vision=provider.vision
                        ),
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            latency_ms = int((time.perf_counter() - t0) * 1000)
            parsed = parse_json_response(content)
            if parsed:
                print(
                    f"[LLM] mode={settings.LLM_SPEED_MODE} provider={provider.name} "
                    f"model={provider.model} vision={provider.vision} "
                    f"latency_ms={latency_ms} billed=yes status=ok"
                )
                return parsed, None, latency_ms, provider.vision
            print(
                f"[LLM] provider={provider.name} model={provider.model} "
                f"latency_ms={latency_ms} billed=yes status=parse_failed"
            )
            return None, "LLM response JSON parse failed", latency_ms, provider.vision
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        err = f"{type(exc).__name__}: {exc}"
        print(
            f"[LLM] provider={provider.name} model={provider.model} "
            f"latency_ms={latency_ms} billed=no status=error {err}"
        )
        return None, err, latency_ms, provider.vision


def call_deepseek(
    query: str,
    elements: Optional[List[UIElement]] = None,
    timeout: Optional[int] = None,
    image_base64: Optional[str] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1200,
    speed_mode: Optional[str] = None,
) -> Tuple[Optional[dict], Optional[str], Optional[int], Optional[str], bool]:
    """
    Returns:
        (parsed_response, error_message, latency_ms, llm_provider, llm_used_vision)
    """
    reload_settings()
    mode = _resolve_speed_mode(speed_mode)
    use_vision = mode == "precision" and bool(image_base64)
    if mode == "fast":
        max_tokens = min(max_tokens, 600)

    chain = (
        _llm_provider_chain_fast_fallback(speed_mode=mode)
        if mode == "fast"
        else _llm_provider_chain(speed_mode=mode)
    )
    if not chain:
        return None, "LLM_API_KEY not configured", None, None, False

    max_elements = 15 if mode == "fast" else 25
    element_text = (
        serialize_elements(elements, max_count=max_elements)
        if elements
        else "（未检测到 UI 元素）"
    )
    if system_prompt is not None:
        prompt = (
            system_prompt.format(element_list=element_text)
            if "{element_list}" in system_prompt
            else system_prompt
        )
    elif mode == "fast":
        prompt = FAST_SYSTEM_PROMPT.format(element_list=element_text)
    else:
        prompt = SYSTEM_PROMPT.format(element_list=element_text)

    vision_image = image_base64 if use_vision else None
    errors: List[str] = []
    total_ms = 0
    used_vision = False
    for i, provider in enumerate(chain):
        if i > 0:
            print(f"[LLM] fallback -> provider={provider.name} model={provider.model}")
        parsed, err, latency_ms, prov_vision = _call_provider_once(
            provider,
            prompt=prompt,
            query=query,
            image_base64=vision_image,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        total_ms += latency_ms or 0
        if parsed:
            if prov_vision:
                used_vision = True
            return parsed, None, total_ms, provider.name, used_vision
        if err:
            errors.append(f"{provider.name}: {err}")

    combined = "; ".join(errors) if errors else "all providers failed"
    return None, combined, total_ms or None, None, used_vision


def probe_llm_chat(timeout: float = 10.0, max_tokens: int = 5) -> Tuple[bool, str, int]:
    chain = _llm_provider_chain(speed_mode="fast")
    if not chain:
        return False, "LLM_API_KEY not configured", 0

    provider = chain[0]
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=_httpx_timeout(timeout)) as client:
            response = client.post(
                f"{provider.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": provider.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": max_tokens,
                },
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if response.status_code == 200:
                return True, f"model={provider.model} ok", latency_ms
            return False, f"HTTP {response.status_code}: {response.text[:200]}", latency_ms
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return False, str(exc), latency_ms


def parse_json_response(content: str) -> Optional[dict]:
    if not content:
        return None
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass
    json_match = re.search(r"\{[\s\S]*\}", content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def parse_llm_response(content: str) -> Optional[dict]:
    data = parse_json_response(content)
    if data and "steps" in data:
        return data
    return None


def parse_llm_steps(content: str) -> Optional[List[dict]]:
    response = parse_llm_response(content)
    if response is not None:
        return response.get("steps")
    return None
