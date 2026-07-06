"""
Context distillation — fast text-only LLM pre-call to summarize screen content.

Matches OpenGuider's src/context/context-analyzer.js.
Reduces token usage and improves accuracy for the main vision LLM call.
"""

from __future__ import annotations

import logging

from server.config import settings

logger = logging.getLogger(__name__)

DISTILLER_SYSTEM_PROMPT = """You are a screen context distiller. Your job is to extract the most relevant information from raw screen text data to help another AI understand the user's current screen.

Given the user's query and the raw text detected on screen, produce a concise summary in English (or the user's language).

## Output Format
Respond with a single paragraph, no markdown. Include:
1. What application/window the user appears to be in
2. Key visible UI elements (buttons, menus, text fields) relevant to the user's query
3. Any important text or labels visible on screen

Be brief — maximum 3-4 sentences."""


def distill_screen_context(
    user_query: str,
    ocr_text: str = "",
    window_info: str = "",
) -> str:
    """Run a fast text-only LLM call to extract relevant screen context.

    Args:
        user_query: The user's original task description
        ocr_text: Raw OCR text from screen (optional)
        window_info: Window enumeration info (optional)

    Returns:
        Distilled context string to inject into the main LLM prompt
    """
    if not settings.DISTILLATION_ENABLED:
        return ""

    raw_context_parts = []
    if window_info:
        raw_context_parts.append(f"Active windows:\n{window_info}")
    if ocr_text:
        # Truncate very long OCR output
        truncated = ocr_text[:2000] if len(ocr_text) > 2000 else ocr_text
        raw_context_parts.append(f"On-screen text:\n{truncated}")

    raw_context = "\n\n".join(raw_context_parts)
    if not raw_context.strip():
        return ""

    try:
        from server.services.llm.providers import call_llm

        summary = call_llm(
            user_text=f"User query: {user_query}\n\nRaw screen data:\n{raw_context}",
            system_prompt=DISTILLER_SYSTEM_PROMPT,
            provider=None,  # Use default provider
            temperature=0.1,
            max_tokens=512,
            timeout=settings.DISTILLATION_TIMEOUT,
        )
        logger.info(f"Distilled context ({len(summary)} chars)")
        return f"\n\n[Screen Context]\n{summary.strip()}"
    except Exception as e:
        logger.warning(f"Distillation failed (non-fatal): {e}")
        return ""


def build_enriched_query(
    user_query: str,
    ocr_text: str = "",
    window_info: str = "",
) -> str:
    """Enrich user query with distilled screen context.

    Returns the original query with context appended (or just the query if distillation disabled).
    """
    if not settings.DISTILLATION_ENABLED:
        return user_query

    context = distill_screen_context(user_query, ocr_text, window_info)
    if context:
        return user_query + context
    return user_query
