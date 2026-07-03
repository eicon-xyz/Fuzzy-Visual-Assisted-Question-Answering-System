"""
Real-time context distillation via fast text-only LLM call.

Takes raw perception data (OCR text, window titles, UI element names)
and distills it into a concise summary for the main multimodal LLM.

Python equivalent of OpenGuider's context/context-analyzer.js.

The key insight: instead of stuffing hundreds of raw OCR tokens into
the expensive multimodal prompt, we use a fast/cheap text-only model
to extract only what's relevant to the user's current goal.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Any

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class PerceptionContext:
    """Aggregated pre-LLM perception data ready for distillation."""
    ocr_result: Any = None  # OCRResult from perception/ocr_engine
    window_info: Any = None  # WindowInfo from perception/window_enum
    matched_elements: List[Any] = field(default_factory=list)
    ui_elements: List[Any] = field(default_factory=list)


# ── Distillation prompt ───────────────────────────────────────────────────────


DISTILLATION_SYSTEM_PROMPT = """You are a screen state analyst. Your job is to extract only the facts from the raw screen data that are RELEVANT to the user's current request.

Rules:
1. Only mention things that exist in the data - never hallucinate
2. Be concise - use short bullet points
3. Focus on elements whose text or function relates to the user's goal
4. Include window titles, visible text, and interactive element names
5. Note the cursor position if it seems relevant
6. Do NOT make recommendations or draw conclusions - just report facts
7. If nothing is relevant, say "No relevant screen elements detected."
8. Respond in the same language as the user's request

Format your response as a short bulleted list."""


def build_raw_context_string(context: PerceptionContext) -> str:
    """Build a raw text dump of all perception data for the distillation LLM.

    This is the input to the fast text-only model.
    """
    parts = []

    # Window info
    if context.window_info:
        wi = context.window_info
        parts.append("=== WINDOWS ===")
        if wi.focused_window:
            parts.append(f"Focused: {wi.focused_window.title}")
        for w in (wi.windows or [])[:10]:
            if not w.minimized:
                parts.append(f"  Visible: {w.title}")
        if wi.cursor_position:
            parts.append(f"Cursor: ({wi.cursor_position[0]}, {wi.cursor_position[1]})")

    # OCR text
    if context.ocr_result:
        ocr = context.ocr_result
        parts.append("\n=== SCREEN TEXT (OCR) ===")
        if ocr.lines:
            for line in ocr.lines[:50]:
                parts.append(f"  {line.text}")
        elif ocr.text:
            parts.append(f"  {ocr.text[:500]}")

    # Matched elements
    if context.matched_elements:
        parts.append("\n=== MATCHED ELEMENTS ===")
        for el in context.matched_elements[:20]:
            text = getattr(el, 'text', str(el))
            score = getattr(el, 'score', 0)
            parts.append(f"  {text} (score={score:.2f})")

    # UI elements
    if context.ui_elements:
        parts.append("\n=== UI ELEMENTS ===")
        for el in context.ui_elements[:25]:
            if hasattr(el, 'name') and hasattr(el, 'control_type'):
                parts.append(f"  {el.control_type}: {el.name}")
            elif hasattr(el, 'text') and hasattr(el, 'element_type'):
                parts.append(f"  {el.element_type}: {el.text}")

    return "\n".join(parts) if parts else "(No screen data available)"


async def analyze_context(
    user_prompt: str,
    context: PerceptionContext,
    settings=None,
) -> str:
    """Distill raw perception data into a concise context summary.

    Maps to OpenGuider's context-analyzer.js analyzeContext().

    Uses a fast text-only LLM call to avoid burning multimodal tokens
    on raw OCR dumps. The distilled summary is then appended to the
    main multimodal prompt.

    Args:
        user_prompt: The user's original query/goal
        context: Aggregated PerceptionContext with OCR, windows, elements
        settings: Optional Config with LLM provider settings

    Returns:
        Distilled context string to append to the main prompt,
        or empty string if distillation is unavailable
    """
    raw_context = build_raw_context_string(context)

    if not raw_context or "No screen data" in raw_context:
        return ""

    # Try a fast LLM call for distillation
    try:
        from server_v2.services.llm.client import call_llm

        messages = [
            {"role": "system", "content": DISTILLATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"User request: {user_prompt}\n\n"
                    f"Screen data:\n{raw_context}\n\n"
                    f"Extract only the facts relevant to the user's request."
                ),
            },
        ]

        result = await call_llm(
            messages=messages,
            settings=settings,
            max_tokens=300,  # Short summary
            temperature=0.0,  # Factual, no creativity
        )

        if result and isinstance(result, str):
            summary = result.strip()
            if summary and "no relevant" not in summary.lower():
                logger.debug(f"Context distilled: {len(raw_context)} chars -> {len(summary)} chars")
                return summary

    except Exception as e:
        logger.warning(f"Context distillation failed: {e}")

    # Fallback: return raw context (truncated)
    return f"Screen context (raw):\n{raw_context[:800]}"
