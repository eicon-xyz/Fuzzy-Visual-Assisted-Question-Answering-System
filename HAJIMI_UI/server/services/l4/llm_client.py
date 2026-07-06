"""L4 专用 LLM 客户端（独立于 L3 client / speed_mode 链）。"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from server.config import settings
from server.services.l4.config import get_l4_settings
from server.services.l4.image_utils import clean_base64
from server.services.llm.wire import post_llm, resolve_wire_api

logger = logging.getLogger(__name__)


def _credentials_for_model(model: str) -> tuple[str, str, str]:
    """按模型选择 API：deepseek-* 走官方 Chat；其余走 LLM 主配置。"""
    name = (model or "").lower()
    if "deepseek" in name and settings.DEEPSEEK_API_KEY:
        base = (settings.DEEPSEEK_BASE_URL or "https://api.deepseek.com").rstrip("/")
        return settings.DEEPSEEK_API_KEY, base, "chat"
    api_key = settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY or ""
    base_url = (settings.LLM_BASE_URL or settings.DEEPSEEK_BASE_URL or "").rstrip("/")
    wire = resolve_wire_api(base_url)
    return api_key, base_url, wire


def call_l4_llm(
    *,
    role: str,
    system: str,
    user: str,
    image_b64: Optional[str] = None,
    vision: bool = False,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
) -> tuple[str, Dict[str, Any]]:
    cfg = get_l4_settings()

    model = cfg.locator_model if vision else cfg.planner_model
    if role == "planner":
        model = cfg.planner_model
    elif role == "locator":
        model = cfg.locator_model

    api_key, base_url, wire = _credentials_for_model(model)
    if not api_key or not base_url:
        raise RuntimeError("L4 LLM: API key or base URL not configured")

    tok = max_tokens or (cfg.locator_max_tokens if vision else cfg.planner_max_tokens)
    tmo = timeout or (cfg.locator_timeout if vision else cfg.planner_timeout)

    raw_b64 = clean_base64(image_b64) if image_b64 else None

    t0 = time.perf_counter()
    content, usage = post_llm(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system=system,
        user=user,
        image_b64=raw_b64,
        vision=vision,
        max_tokens=tok,
        timeout=tmo,
        wire_api=wire,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    meta = {
        "model": model,
        "role": role,
        "vision": vision,
        "wire_api": wire,
        "latency_ms": elapsed_ms,
        "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "completion_tokens": usage.get("completion_tokens")
        or usage.get("output_tokens"),
    }
    logger.info(
        "L4 LLM %s model=%s wire=%s latency=%dms",
        role,
        model,
        wire,
        elapsed_ms,
    )
    return content, meta


def parse_json_steps(raw: str) -> list[dict]:
    """从 planner 输出中提取 steps JSON。"""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict) and "steps" in obj:
            return obj["steps"]
    except json.JSONDecodeError:
        pass

    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("L4 planner: cannot parse steps JSON from LLM output")
