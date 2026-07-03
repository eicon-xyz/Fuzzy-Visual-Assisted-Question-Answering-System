"""
Evaluator chain — checks if the user completed a step successfully.

Python equivalent of OpenGuider's agent/evaluator-chain.js.

Takes the current plan step and a new screenshot, then determines
whether the step was completed. Outputs a status (done/not_done/
blocked/uncertain) and a suggested action.
"""

import logging
from typing import List, Dict, Optional, Any

from .llm_client import invoke_structured_chain
from .schemas import EvaluationOutput

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

EVALUATOR_SYSTEM_PROMPT = """You are a step completion evaluator. Your job is to compare what the user was supposed to do with what actually happened on screen.

## Output Format
Return JSON:
```json
{
  "status": "done",
  "confidence": 0.9,
  "rationale": "The expected dialog window is now visible",
  "suggested_action": "advance",
  "assistant_response": "Great, the settings window opened successfully!"
}
```

## Status values
- "done": The step was clearly completed
- "not_done": The step was attempted but not completed
- "blocked": Something prevents completing the step (error, missing permission, etc.)
- "uncertain": Cannot confidently determine if step is done

## Suggested actions
- "advance": Move to next step
- "repeat_guidance": Show the same step again
- "replan": The current plan no longer applies, need a new plan

## Rules
1. Be CONSERVATIVE — if uncertain, prefer "not_done" or "uncertain" over "done"
2. Only suggest "replan" if the user is clearly on a different path
3. Confidence below 0.6 should be "uncertain"
4. The assistant_response should be supportive and specific
5. Compare the instruction against the CURRENT screen state"""


# ── Template ──────────────────────────────────────────────────────────────────

EVALUATOR_TEMPLATE = """Original goal: {goal}

Current step: {step_title}
Instruction: {step_instruction}
Success criteria: {success_criteria}

{user_note_section}
The user has attempted this step. Compare the current screen against what SHOULD have happened.

Return ONLY valid JSON with your evaluation."""


# ── Chain function ────────────────────────────────────────────────────────────


async def evaluate_step(
    plan: Dict,
    step: Dict,
    images: List[Dict],
    settings: Any,
    user_note: str = "",
    signal: Any = None,
) -> Dict:
    """Evaluate whether the current step was completed.

    Maps to OpenGuider's evaluator-chain.js evaluateStep().

    Args:
        plan: The normalized plan dict
        step: The current step dict
        images: List of screenshot dicts (AFTER user attempted the step)
        settings: Config with LLM provider info
        user_note: Optional user comment
        signal: Optional cancellation signal

    Returns:
        Dict with status, confidence, rationale, suggested_action, assistant_response
    """
    logger.info(f"Evaluating step: {step.get('title', 'unknown')}")

    user_note_section = f"User feedback: {user_note}" if user_note else ""

    try:
        result: EvaluationOutput = await invoke_structured_chain(
            settings=settings,
            system_prompt=EVALUATOR_SYSTEM_PROMPT,
            template=EVALUATOR_TEMPLATE,
            input_data={
                "goal": plan.get("goal", ""),
                "step_title": step.get("title", ""),
                "step_instruction": step.get("instruction", step.get("title", "")),
                "success_criteria": step.get("success_criteria", "步骤指引完成"),
                "user_note_section": user_note_section,
            },
            images=images,
            history=None,
            schema_class=EvaluationOutput,
            signal=signal,
            operation_name="evaluator",
            is_locator=False,
            max_tokens=512,
            temperature=0.2,
        )
    except Exception as e:
        logger.error(f"Evaluator failed: {e}")
        return {
            "status": "uncertain",
            "confidence": 0.5,
            "rationale": f"Evaluator error: {str(e)[:100]}",
            "suggested_action": "advance",
            "assistant_response": "",
        }

    output = result.model_dump()
    logger.info(
        f"Evaluation: status={output.get('status')}, "
        f"confidence={output.get('confidence')}, "
        f"action={output.get('suggested_action')}"
    )
    return output
