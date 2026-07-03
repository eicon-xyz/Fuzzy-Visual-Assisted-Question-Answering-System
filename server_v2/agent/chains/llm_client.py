"""
Structured chain wrapper for LLM calls.

Python equivalent of OpenGuider's agent/llm-client.js.

Provides invokeStructuredChain: a reusable pipeline that:
1. Formats a prompt template with input variables
2. Calls the LLM with the formatted prompt + images
3. Parses the JSON response
4. Validates against a Pydantic schema

All four chains (planner, executor, evaluator, replanner) use this.
"""

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel

from .schemas import extract_json_object, parse_structured_json, format_user_error

logger = logging.getLogger(__name__)


async def invoke_structured_chain(
    settings,
    system_prompt: str,
    template: Optional[str],
    input_data: Dict[str, Any],
    images: Optional[List[Dict]] = None,
    history: Optional[List[Dict]] = None,
    schema_class: Optional[Type[BaseModel]] = None,
    signal=None,  # For cancellation
    operation_name: str = "structured_chain",
    is_locator: bool = False,
    max_tokens: int = 2048,
    temperature: float = 0.3,
    on_chunk: Optional[Callable] = None,
) -> Any:
    """Invoke a structured LLM chain and validate the output.

    The pattern (matching OpenGuider's llm-client.js):
        PromptTemplate -> LLM Call -> JSON Parse -> Pydantic Validate

    Args:
        settings: Config/settings object with LLM provider info
        system_prompt: System prompt for the LLM
        template: Optional message template string (with {placeholder} vars)
        input_data: Dict of values to fill template placeholders
        images: Optional list of {base64Jpeg, width, height} image dicts
        history: Optional list of {role, content} message history
        schema_class: Pydantic model class for output validation
        signal: Optional cancellation signal
        operation_name: Name for logging
        is_locator: Whether this is a locator chain (enables [POINT] tag parsing)
        max_tokens: Max tokens for LLM response
        temperature: LLM temperature
        on_chunk: Optional callback(chunk_text) for streaming

    Returns:
        Validated Pydantic model instance, or raw dict if no schema_class

    Raises:
        ValueError: If LLM returns unparseable response
        Exception: Re-raised after formatting user-friendly error
    """
    from server_v2.services.llm.client import call_llm

    # Format user message from template
    user_message = template.format(**input_data) if template else str(input_data)

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]

    if history:
        messages.extend(history)

    # Add image content if provided (multimodal)
    if images and len(images) > 0:
        # Build content array with text + images
        content = [{"type": "text", "text": user_message}]
        for img in images:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img.get('base64Jpeg', img.get('base64', ''))}",
                },
            })
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})

    # Call LLM
    start_time = time.time()
    logger.info(f"[{operation_name}] Starting LLM call...")

    try:
        raw_response = await call_llm(
            messages=messages,
            settings=settings,
            max_tokens=max_tokens,
            temperature=temperature,
            signal=signal,
        )
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{operation_name}] LLM call failed after {elapsed:.1f}s: {e}")
        raise ValueError(format_user_error(e)) from e

    elapsed = time.time() - start_time
    logger.info(f"[{operation_name}] LLM call completed in {elapsed:.1f}s")

    if not raw_response:
        raise ValueError("LLM returned empty response")

    # Parse and validate
    try:
        if schema_class:
            result = parse_structured_json(
                raw_response,
                schema_class,
                is_locator=is_locator,
            )
        else:
            result = extract_json_object(raw_response)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            f"[{operation_name}] JSON parse failed: {e}. "
            f"Raw response (first 200 chars): {str(raw_response)[:200]}"
        )
        raise ValueError(
            f"AI returned unparseable response for {operation_name}: {str(e)[:100]}"
        ) from e

    return result
