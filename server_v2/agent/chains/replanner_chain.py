"""
Replanner chain — fixes the plan when the user is stuck or off-track.

Python equivalent of OpenGuider's agent/replanner-chain.js.

Takes the original goal, current plan, and evaluator feedback,
then generates a revised plan with new remaining steps.
Completed steps are NOT repeated.
"""

import logging
from typing import List, Dict, Optional, Any

from .llm_client import invoke_structured_chain
from .schemas import ReplannerOutput

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

REPLANNER_SYSTEM_PROMPT = """You are a plan repair specialist. The user's original plan is no longer working — either they're stuck, something changed on screen, or the approach was wrong.

## Your Task
Create a REVISED plan that:
1. Keeps COMPLETED steps unchanged (do not repeat them)
2. Replaces remaining steps with a better approach
3. Accounts for the current screen state
4. Acknowledges what went wrong briefly

## Output Format
Return JSON:
```json
{
  "assistant_response": "I see the button isn't where I expected. Let me suggest a different approach...",
  "goal": "original goal unchanged",
  "steps": [
    {"id": "step_N", "title": "...", "instruction": "...", ...}
  ]
}
```

## Rules
1. ONLY return remaining steps (completed ones are already done)
2. Restate the original goal verbatim
3. The assistant_response should be empathetic about the difficulty
4. If the screen looks different than expected, adapt the steps
5. Return at least 1 step"""


# ── Template ──────────────────────────────────────────────────────────────────

REPLANNER_TEMPLATE = """Original goal: {goal}

Plan so far:
{plan_summary}

Problem: The current step "{current_step_title}" could not be completed.
Reason: {problem_reason}
Evaluation status: {eval_status} (confidence: {eval_confidence})

The user needs a revised plan. Create new remaining steps.
Return ONLY valid JSON."""


# ── Chain function ────────────────────────────────────────────────────────────


async def replan_goal(
    plan: Dict,
    step: Dict,
    evaluation: Dict,
    images: List[Dict],
    settings: Any,
    signal: Any = None,
) -> Dict:
    """Generate a revised plan when the user is stuck.

    Maps to OpenGuider's replanner-chain.js replanGoal().

    Args:
        plan: The normalized plan dict
        step: The step that failed
        evaluation: Evaluator output dict {status, confidence, rationale, ...}
        images: Latest screenshots
        settings: Config with LLM provider info
        signal: Optional cancellation signal

    Returns:
        Dict with assistant_response and plan (revised)
    """
    logger.info(f"Replanning from step: {step.get('title', 'unknown')}")

    # Build plan summary (completed vs remaining steps)
    steps = plan.get("steps", [])
    current_idx = plan.get("current_step_index", 0)

    completed = []
    remaining = []
    for i, s in enumerate(steps):
        summary = f"  [{s.get('status', '?')}] Step {i+1}: {s.get('title', '')}"
        if i < current_idx:
            completed.append(summary)
        else:
            remaining.append(summary)

    plan_summary = (
        f"Completed steps:\n" + "\n".join(completed) +
        f"\nRemaining steps:\n" + "\n".join(remaining)
    )

    try:
        result: ReplannerOutput = await invoke_structured_chain(
            settings=settings,
            system_prompt=REPLANNER_SYSTEM_PROMPT,
            template=REPLANNER_TEMPLATE,
            input_data={
                "goal": plan.get("goal", ""),
                "plan_summary": plan_summary,
                "current_step_title": step.get("title", ""),
                "problem_reason": evaluation.get("rationale", "未知原因"),
                "eval_status": evaluation.get("status", "blocked"),
                "eval_confidence": evaluation.get("confidence", 0.5),
            },
            images=images,
            history=None,
            schema_class=ReplannerOutput,
            signal=signal,
            operation_name="replanner",
            is_locator=False,
            max_tokens=2048,
            temperature=0.4,
        )
    except Exception as e:
        logger.error(f"Replanner failed: {e}")
        # Return original remaining steps as fallback
        return {
            "assistant_response": "我重新评估了计划，建议继续按原步骤尝试。",
            "plan": dict(plan),  # shallow copy
        }

    output = result.model_dump()

    # Build revised plan: keep completed steps + new remaining steps
    completed_steps = [
        dict(s) for s in steps[:current_idx]
    ]
    new_steps = output.get("steps", [])

    # Normalize new steps
    for i, s in enumerate(new_steps):
        s["status"] = "pending" if i > 0 else "active"
        s.setdefault("coordinate", None)
        s.setdefault("label", None)
        s.setdefault("target_element_id", None)
        s.setdefault("explanation", "")

    revised_plan = {
        **plan,
        "goal": output.get("goal", plan.get("goal", "")),
        "steps": completed_steps + new_steps,
        "current_step_index": len(completed_steps),  # First new step
        "total_steps": len(completed_steps) + len(new_steps),
        "status": "executing",
        "updated_at": "",
    }

    logger.info(
        f"Replanner: {len(completed_steps)} completed + "
        f"{len(new_steps)} new steps"
    )

    return {
        "assistant_response": output.get("assistant_response", ""),
        "plan": revised_plan,
    }
