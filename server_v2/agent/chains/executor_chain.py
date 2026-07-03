"""
Executor/Locator chain — finds where to point on screen for a step.

Python equivalent of OpenGuider's agent/executor-chain.js.

Given a plan step and a screenshot, this chain returns the normalized
(0-1000) coordinate of the target UI element. Outputs [POINT:x,y:label]
tags for downstream parsing.
"""

import logging
from typing import List, Dict, Optional, Any

from .llm_client import invoke_structured_chain
from .schemas import StepPointerOutput

logger = logging.getLogger(__name__)

# ── System prompts ────────────────────────────────────────────────────────────

EXECUTOR_SYSTEM_PROMPT = """You are a precise UI element locator. Your job is to find exactly where on screen the user should click or look.

## Coordinate System
Use a 0-1000 normalized coordinate system:
- (0, 0) = top-left corner of the screen
- (1000, 1000) = bottom-right corner
- (500, 500) = center

## Output Format
Return JSON:
```json
{
  "coordinate": {"x": 500, "y": 300},
  "label": "button name or element description",
  "explanation": "how you identified this element",
  "should_point": true
}
```

If you CANNOT find the target element, set:
- coordinate: null
- should_point: false
- explanation: why you couldn't find it

## Rules
1. Be PRECISE with coordinates — they guide the user's mouse
2. The label should match what the user sees on screen
3. If the element is clearly visible, set should_point = true
4. Prefer center of the target element
5. Account for scroll bars, toolbars, and window chrome
6. If uncertain, estimate conservatively"""


STRICT_LOCATOR_SYSTEM_PROMPT = """You are a UI element locator in STRICT mode. You MUST return a coordinate, even if you're not 100% sure.

## Rules
1. You MUST return a best-guess coordinate — never return null
2. Explain your uncertainty in the explanation field
3. Guess the most likely position based on common UI patterns:
   - Settings/Preferences: usually under File/Edit menus or a gear icon
   - OK/Cancel buttons: bottom-right of dialog
   - Search: top-right area
   - File operations: under File menu or ribbon
   - Tabs: top of the content area

Return JSON with a coordinate ALWAYS."""


# ── Template ──────────────────────────────────────────────────────────────────

EXECUTOR_TEMPLATE = """Current step: {step_title}
Instruction: {step_instruction}

Screen context:
{screen_context}

Find the target element "{step_title}" on the screen.
Return the coordinate in 0-1000 range where the user should point.

{user_note_section}
Return ONLY valid JSON."""


# ── Chain function ────────────────────────────────────────────────────────────


async def locate_step_target(
    plan: Dict,
    step: Dict,
    images: List[Dict],
    settings: Any,
    user_note: str = "",
    signal: Any = None,
    force_pointing: bool = False,
    preprocessing_context: Optional[Dict] = None,
) -> Dict:
    """Locate the target element for a plan step on screen.

    Maps to OpenGuider's executor-chain.js locateStepTarget().

    Args:
        plan: The normalized plan dict
        step: The current step dict
        images: List of screenshot dicts [{base64Jpeg, width, height}]
        settings: Config with LLM provider info
        user_note: Optional user-provided note/clarification
        signal: Optional cancellation signal
        force_pointing: If True, retry with strict prompt on no-coordinate
        preprocessing_context: Optional dict from InteractionPipeline.preprocess()

    Returns:
        Dict with coordinate, label, explanation, should_point
    """
    logger.info(f"Locating target for step: {step.get('title', 'unknown')}")

    # Build screen context from preprocessing
    screen_context = ""
    if preprocessing_context:
        from context.prompt_enricher import build_enriched_prompt, EnrichContext
        ctx = EnrichContext(
            ocr_result=preprocessing_context.get("ocr_result"),
            window_info=preprocessing_context.get("window_info"),
            matched_elements=preprocessing_context.get("matched_elements", []),
            distilled_summary=preprocessing_context.get("distilled_summary", ""),
        )
        screen_context = build_enriched_prompt("", ctx, use_distilled=True)
    else:
        screen_context = "（无屏幕上下文）"

    user_note_section = f"User note: {user_note}" if user_note else ""

    try:
        result: StepPointerOutput = await invoke_structured_chain(
            settings=settings,
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
            template=EXECUTOR_TEMPLATE,
            input_data={
                "step_title": step.get("title", ""),
                "step_instruction": step.get("instruction", step.get("title", "")),
                "screen_context": screen_context,
                "user_note_section": user_note_section,
            },
            images=images,
            history=None,
            schema_class=StepPointerOutput,
            signal=signal,
            operation_name="executor",
            is_locator=True,
            max_tokens=1024,
            temperature=0.2,
        )
    except Exception as e:
        logger.error(f"Executor failed: {e}")
        # Return null coordinate on failure
        return {
            "coordinate": None,
            "label": None,
            "explanation": f"Locator error: {str(e)[:100]}",
            "should_point": False,
        }

    output = result.model_dump()

    # Strict mode retry: if force_pointing and no coordinate, retry
    if force_pointing and not output.get("coordinate"):
        logger.info("Strict mode retry: forcing coordinate output")
        try:
            strict_result: StepPointerOutput = await invoke_structured_chain(
                settings=settings,
                system_prompt=STRICT_LOCATOR_SYSTEM_PROMPT,
                template=EXECUTOR_TEMPLATE,
                input_data={
                    "step_title": step.get("title", ""),
                    "step_instruction": step.get("instruction", step.get("title", "")),
                    "screen_context": screen_context,
                    "user_note_section": user_note_section,
                },
                images=images,
                history=None,
                schema_class=StepPointerOutput,
                signal=signal,
                operation_name="executor_strict",
                is_locator=True,
                max_tokens=1024,
                temperature=0.1,
            )
            output = strict_result.model_dump()
        except Exception as e:
            logger.warning(f"Strict mode executor also failed: {e}")

    logger.info(
        f"Locator result: coord={output.get('coordinate')}, "
        f"label={output.get('label')}, should_point={output.get('should_point')}"
    )
    return output
