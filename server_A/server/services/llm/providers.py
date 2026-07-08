"""
HAJIMI_UI — Multi-Provider LLM Client (sync)

Transplanted from OpenSource hajimi-og-v2/server/services/llm/providers.py.
Matches OpenGuider's src/ai/index.js architecture.
Native [POINT:x,y:label] tag parser, DEFAULT_SYSTEM_PROMPT, multi-provider streaming.
Adapted for sync usage (HAJIMI_UI uses sync FastAPI routes).
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from server.config import settings

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# DEFAULT_SYSTEM_PROMPT — mirrors OpenGuider's src/ai/index.js exactly
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_SYSTEM_PROMPT = """You are HAJIMI, a helpful AI companion that lives in the Windows system tray.
You can see the user's screen when they share it. Keep replies concise unless asked to elaborate.
Be direct and conversational. When the user asks about something on screen, reference what you see.

CRITICAL INSTRUCTION FOR ELEMENT POINTING:
If the user asks you to show, point to, or find a specific UI element on the screen, YOU MUST append a special tag to your answer.
Format: [POINT:x,y:label]
IMPORTANT COORDINATE RULES:
1. You MUST provide coordinates on a normalized 0 to 1000 scale.
2. X=0, Y=0 is the TOP-LEFT corner.
3. X=1000, Y=1000 is the BOTTOM-RIGHT corner.
4. Do NOT output absolute pixels. ONLY output numbers between 0 and 1000.
Example: "Here is the submit button. [POINT:850,450:Submit Button]"
If no pointing is needed, DO NOT invent coordinates, just reply normally or append [POINT:none].
NEVER provide coordinates in regular text like "(x, y)". ONLY use the [POINT:x,y:label] tag format.

MULTI-SCREEN RULE:
When you receive screenshots from multiple screens, you MUST append the screen number to the POINT tag.
Format: [POINT:x,y:label:screenN]
If there is only one screen, you may omit :screenN.
Coordinates are always on the 0-1000 scale relative to that specific screen's image.
"""

# ═══════════════════════════════════════════════════════════════════════════
# Point Tag Parser — mirrors OpenGuider's parsePointTag() exactly
# ═══════════════════════════════════════════════════════════════════════════

POINT_REGEX = re.compile(
    r"\[POINT:(?:none|([\d.]+)\s*,\s*([\d.]+)(?::([^\]:]+))?(?::screen(\d+))?)\]",
    re.IGNORECASE,
)


def parse_point_tags(full_text: str) -> dict:
    """Matches OpenGuider's parsePointTag() return shape exactly.
    Returns: {spokenText, coordinate: {x, y}|None, label, screenNumber}"""
    first_coord = None
    first_label = "element"
    first_screen = None

    def replacer(m):
        nonlocal first_coord, first_label, first_screen
        x, y, label, scr = m.group(1), m.group(2), m.group(3), m.group(4)
        if x and y and first_coord is None:
            first_coord = {"x": float(x), "y": float(y)}
            if label:
                first_label = label
            if scr:
                first_screen = int(scr)
        return ""

    clean = POINT_REGEX.sub(replacer, full_text).strip()

    if first_coord is None:
        # Fallback: try (x, y) format
        fallback = re.search(r"\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\)", full_text)
        if fallback:
            return {
                "spokenText": full_text.replace(fallback[0], "").strip(),
                "coordinate": {"x": float(fallback[1]), "y": float(fallback[2])},
                "label": "element",
                "screenNumber": None,
            }
        return {
            "spokenText": clean,
            "coordinate": None,
            "label": None,
            "screenNumber": None,
        }

    return {
        "spokenText": clean,
        "coordinate": first_coord,
        "label": first_label,
        "screenNumber": first_screen,
    }


# ═══════════════════════════════════════════════════════════════════════════
# JSON extraction (mirrors OpenGuider's extractJSONObject in schemas.js)
# ═══════════════════════════════════════════════════════════════════════════


def extract_json_object(raw: str) -> dict:
    """Extract JSON object from raw LLM text. Handles code fences,
    leading whitespace/newlines, and repairs Qwen quirks."""
    # Strip code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"```", "", cleaned)
    # Handle BOM / zero-width characters
    cleaned = cleaned.replace("﻿", "").replace("​", "")
    # Strip leading whitespace/newlines before first {
    cleaned = cleaned.strip()

    # Try to extract JSON from thinking text by finding the LAST complete JSON block
    cleaned = cleaned.strip()

    # Models that output reasoning before JSON: find the LAST JSON object
    # Scan from the end backwards looking for complete {...} pair
    end = cleaned.rfind("}")
    if end == -1:
        raise ValueError("Model did not return a JSON object.")

    # Find matching opening brace before end
    depth = 0
    start = -1
    for i in range(end, -1, -1):
        if cleaned[i] == "}":
            depth += 1
        elif cleaned[i] == "{":
            depth -= 1
            if depth == 0:
                start = i
                break

    if start == -1 or end <= start:
        raise ValueError("Model did not return a JSON object.")

    snippet = cleaned[start : end + 1]
    # Remove trailing commas before ] or }
    snippet = re.sub(r",\s*(\}|\])", r"\1", snippet)
    # Remove comments
    snippet = re.sub(r"//.*", "", snippet)

    try:
        data = json.loads(snippet)
    except json.JSONDecodeError as e2:
        # Regex: find simple JSON with element_id or goal
        m = re.search(r'\{[^{}]*"(?:element_id|goal)"[^{}]*\}', snippet)
        if m:
            try:
                data = json.loads(m.group())
                return data
            except json.JSONDecodeError:
                pass
        # Repairs: add missing brackets, try ast.literal_eval
        try:
            open_b = snippet.count("{") - snippet.count("}")
            open_s = snippet.count("[") - snippet.count("]")
            fixed = snippet + "}" * open_b + "]" * open_s
            data = json.loads(fixed)
        except Exception:
            try:
                import ast

                data = ast.literal_eval(snippet)
            except Exception:
                raise ValueError(f"JSON parse error: {e2.msg}") from e2

    # Repair: Qwen sometimes returns {"plan": [...]} instead of {"steps": [...]}
    if "plan" in data and "steps" not in data:
        plan_items = data["plan"]
        if isinstance(plan_items, list):
            data["steps"] = [
                (
                    {"title": s[:40], "instruction": s, "successCriteria": s}
                    if isinstance(s, str)
                    else s
                )
                for s in plan_items
            ]

    # Repair: flat string steps
    if "steps" in data:
        data["steps"] = [
            (
                {"title": s[:40], "instruction": s, "successCriteria": s}
                if isinstance(s, str)
                else s
            )
            for s in data["steps"]
        ]

    # Ensure required top-level keys exist
    data.setdefault("goal", "Complete the task")
    data.setdefault("assistantResponse", "I've created a plan for you.")
    data.setdefault("assumptions", [])

    return data


def parse_structured_json(raw: str, is_locator: bool = False) -> dict:
    """Parse structured LLM output with locator fallback.
    Matches OpenGuider's parseStructuredJSON() exactly."""
    if not is_locator:
        return extract_json_object(raw)

    # Locator mode: try JSON, but always harvest [POINT] tags from raw text
    result = {
        "coordinate": None,
        "label": None,
        "explanation": raw,
        "shouldPoint": True,
    }
    try:
        parsed = extract_json_object(raw)
        result["coordinate"] = parsed.get("coordinate")
        result["label"] = parsed.get("label")
        result["explanation"] = parsed.get("explanation", raw)
        result["shouldPoint"] = parsed.get("shouldPoint", True)
    except Exception:
        pass

    # Always harvest [POINT:x,y:label] from raw text as fallback
    m = POINT_REGEX.search(raw)
    if m and m.group(1) and m.group(2):
        result["coordinate"] = {"x": float(m.group(1)), "y": float(m.group(2))}
        if m.group(3):
            result["label"] = m.group(3)
        result["shouldPoint"] = True

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Provider config resolution
# ═══════════════════════════════════════════════════════════════════════════


def _get_provider_config(provider: str | None = None) -> dict:
    """Resolve provider configuration from settings."""
    p = (provider or getattr(settings, "LLM_PROVIDER", "qwen") or "qwen").lower()

    provider_map = {
        "openai": {
            "provider": "openai",
            "api_key": getattr(settings, "OPENAI_API_KEY", "") or settings.LLM_API_KEY,
            "base_url": getattr(settings, "OPENAI_BASE_URL", "")
            or "https://api.openai.com/v1",
            "model": getattr(settings, "OPENAI_MODEL", "") or "gpt-4o",
        },
        "claude": {
            "provider": "claude",
            "api_key": getattr(settings, "CLAUDE_API_KEY", "") or settings.LLM_API_KEY,
            "base_url": "https://api.anthropic.com/v1",
            "model": getattr(settings, "CLAUDE_MODEL", "")
            or "claude-sonnet-4-20250514",
        },
        "gemini": {
            "provider": "gemini",
            "api_key": getattr(settings, "GEMINI_API_KEY", "") or settings.LLM_API_KEY,
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "model": getattr(settings, "GEMINI_MODEL", "") or "gemini-2.5-flash",
        },
        "groq": {
            "provider": "groq",
            "api_key": getattr(settings, "GROQ_API_KEY", "") or settings.LLM_API_KEY,
            "base_url": "https://api.groq.com/openai/v1",
            "model": getattr(settings, "GROQ_MODEL", "")
            or "llama-3.2-11b-vision-preview",
        },
        "openrouter": {
            "provider": "openrouter",
            "api_key": getattr(settings, "OPENROUTER_API_KEY", "")
            or settings.LLM_API_KEY,
            "base_url": "https://openrouter.ai/api/v1",
            "model": getattr(settings, "OPENROUTER_MODEL", "")
            or "anthropic/claude-sonnet-4",
        },
        "ollama": {
            "provider": "ollama",
            "api_key": "ollama",
            "base_url": getattr(settings, "OLLAMA_BASE_URL", "")
            or "http://localhost:11434/v1",
            "model": getattr(settings, "OLLAMA_MODEL", "") or "llama3.2-vision",
        },
        "qwen": {
            "provider": "qwen",
            "api_key": getattr(settings, "QWEN_API_KEY", "") or settings.LLM_API_KEY,
            "base_url": getattr(settings, "QWEN_BASE_URL", "")
            or settings.LLM_BASE_URL
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": getattr(settings, "QWEN_MODEL", "")
            or settings.LLM_MODEL
            or "qwen-vl-max",
            "assistant_content_style": "empty_string",  # Qwen-VL-Max requires content="" not content=None
        },
        "glm": {
            "provider": "glm",
            "api_key": getattr(settings, "GLM_API_KEY", "") or settings.LLM_API_KEY,
            "base_url": getattr(settings, "GLM_BASE_URL", "")
            or "https://api.siliconflow.cn/v1",
            "model": getattr(settings, "GLM_MODEL", "") or "THUDM/glm-4-9b-chat",
        },
        "deepseek": {
            "provider": "deepseek",
            "api_key": getattr(settings, "DEEPSEEK_API_KEY", "")
            or settings.LLM_API_KEY,
            "base_url": getattr(settings, "DEEPSEEK_BASE_URL", "")
            or "https://api.deepseek.com",
            "model": getattr(settings, "DEEPSEEK_MODEL", "") or "deepseek-chat",
        },
    }

    if p in provider_map:
        return provider_map[p]

    # Fallback: treat as OpenAI-compatible with LLM_ settings
    return {
        "provider": p,
        "api_key": settings.LLM_API_KEY,
        "base_url": settings.LLM_BASE_URL or "https://api.siliconflow.cn/v1",
        "model": settings.LLM_MODEL or "Qwen/Qwen3.6-35B-A3B",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Image helpers
# ═══════════════════════════════════════════════════════════════════════════


def _strip_data_uri_prefix(image: str) -> str:
    """Strip data URI prefix, return pure base64 string."""
    if "," in image and image.startswith("data:"):
        return image.split(",", 1)[1]
    return image


def _detect_mime(image_base64: str) -> str:
    """Detect MIME type from data URI prefix."""
    if "image/jpeg" in image_base64[:64] or "image/jpg" in image_base64[:64]:
        return "image/jpeg"
    return "image/png"


# ═══════════════════════════════════════════════════════════════════════════
# Sync LLM call (non-streaming) — primary interface
# ═══════════════════════════════════════════════════════════════════════════


def call_llm(
    user_text: str,
    images: list | None = None,
    history: list | None = None,
    system_prompt: str = "",
    provider: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str:
    """Sync LLM call. Returns full response text.
    Matches OpenGuider's streamAIResponse() dispatcher, sync version.

    Args:
        user_text: User message text
        images: List of {"base64Jpeg": str, "label": str} dicts
        history: List of {"role": str, "content": str} dicts
        system_prompt: System prompt (uses DEFAULT_SYSTEM_PROMPT if empty)
        provider: Provider name (openai/claude/gemini/groq/openrouter/ollama/qwen/glm)
        temperature: Sampling temperature
        max_tokens: Max output tokens
        timeout: HTTP timeout in seconds

    Returns:
        Full response text from LLM
    """
    pc = _get_provider_config(provider)
    p = pc["provider"]
    sp = system_prompt or DEFAULT_SYSTEM_PROMPT
    base = pc["base_url"].rstrip("/")

    # Build messages matching OpenGuider's buildOpenAIUserContent
    msgs = [{"role": "system", "content": sp}]
    for h in history or []:
        msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})

    # Build user content with images
    user_content = []
    for img in images or []:
        b64 = img.get("base64Jpeg", img.get("base64", ""))
        if b64:
            mime = _detect_mime(b64)
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{_strip_data_uri_prefix(b64)}"
                    },
                }
            )
            lbl = img.get("label", f"Screen {img.get('screenNumber', '')}")
            user_content.append({"type": "text", "text": f"[{lbl}]"})

    if user_content:
        user_content.append({"type": "text", "text": user_text})
        msgs.append({"role": "user", "content": user_content})
    else:
        msgs.append({"role": "user", "content": user_text})

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {pc['api_key']}",
    }
    if p == "openrouter":
        headers["X-Title"] = "HAJIMI"

    # Adaptive max_tokens for retry on 402/413 errors
    adaptive_tokens = [max_tokens, max_tokens // 2, max_tokens // 4, 128, 64, 32]
    # Deduplicate preserving order
    seen = set()
    adaptive_tokens = [t for t in adaptive_tokens if not (t in seen or seen.add(t))]  # type: ignore

    last_error = None
    for attempt, attempt_tokens in enumerate(adaptive_tokens):
        body = {
            "model": pc["model"],
            "messages": msgs,
            "max_tokens": attempt_tokens,
            "temperature": temperature,
        }
        # Force non-thinking mode on Qwen models
        if pc.get("provider") == "qwen" and "extra_body" not in body:
            try:
                body["enable_thinking"] = False
            except Exception:
                pass
        url = f"{base}/chat/completions"

        logger.info(
            f"LLM call: provider={p} model={pc['model']} tokens={attempt_tokens} url={url[:80]}"
        )

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=body)

                if (
                    response.status_code in (402, 413)
                    and attempt < len(adaptive_tokens) - 1
                ):
                    logger.warning(
                        f"LLM {response.status_code}, retrying with {adaptive_tokens[attempt + 1]} tokens"
                    )
                    continue

                if response.status_code == 429 and attempt < len(adaptive_tokens) - 1:
                    retry_after = response.headers.get("Retry-After", "2")
                    import time

                    try:
                        time.sleep(float(retry_after))
                    except ValueError:
                        time.sleep(2**attempt)
                    continue

                response.raise_for_status()
                data = response.json()
                msg = data["choices"][0]["message"]
                content = msg.get("content", "") or ""
                # Qwen thinking models put response in reasoning_content
                if not content:
                    content = msg.get("reasoning_content", "") or ""
                # Sometimes there's content but it's thinking, try to extract the real answer
                if content and len(content) > 500:
                    # Check if it looks like a thinking block
                    import re

                    json_match = re.search(
                        r'\{[\s\S]*"goal"[\s\S]*"steps"[\s\S]*\}', content
                    )
                    if json_match:
                        content = json_match.group(0)
                return content

        except httpx.HTTPStatusError as e:
            last_error = e
            if attempt < len(adaptive_tokens) - 1:
                continue
            break
        except Exception as e:
            last_error = e
            if attempt < len(adaptive_tokens) - 1:
                continue
            break

    raise RuntimeError(
        f"LLM call failed after {len(adaptive_tokens)} attempts: {last_error}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Convenience: call LLM and get parsed JSON
# ═══════════════════════════════════════════════════════════════════════════


def call_llm_json(
    user_text: str,
    images: list | None = None,
    history: list | None = None,
    system_prompt: str = "",
    provider: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 120,
    is_locator: bool = False,
) -> dict:
    """Call LLM and parse response as JSON.
    Returns parsed dict or raises."""
    raw = call_llm(
        user_text=user_text,
        images=images,
        history=history,
        system_prompt=system_prompt,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    return parse_structured_json(raw, is_locator=is_locator)


# ═══════════════════════════════════════════════════════════════════════════
# Legacy compatibility: call_deepseek equivalent via providers
# ═══════════════════════════════════════════════════════════════════════════


def call_vision_llm(
    query: str,
    image_base64: str | None = None,
    system_prompt: str = "",
    provider: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str:
    """Simple vision LLM call with optional image. Returns raw text.
    Replaces the old call_deepseek pattern."""
    images = None
    if image_base64:
        images = [{"base64Jpeg": image_base64, "label": "Screen"}]

    return call_llm(
        user_text=query,
        images=images,
        system_prompt=system_prompt,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
