"""
Planner chain — converts a user goal + screenshot into a structured plan.

Python equivalent of OpenGuider's agent/planner-chain.js.

The planner takes the user's natural language goal and the current
screen state, then generates a sequence of steps with titles,
instructions, success criteria, and guidance modes.
"""

import logging
from typing import List, Dict, Optional, Any

from .llm_client import invoke_structured_chain
from .schemas import PlannerOutput
from .schemas import PlanStepDef

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

PLANNER_SYSTEM_PROMPT = """You are a desktop guidance assistant. Your task is to create a step-by-step plan to help the user accomplish their goal.

## Core Rule
The user's stated goal is the ONLY source of truth. Never substitute a different goal from what you see on screen. If the screen doesn't match the goal, still plan for the GOAL, not the screen.

## Output Format
Return a JSON object with this exact structure:
```json
{
  "goal": "restated user goal",
  "assistant_response": "brief natural language acknowledgement to the user",
  "assumptions": ["assumption 1", "assumption 2"],
  "steps": [
    {
      "id": "step_1",
      "title": "short action title",
      "instruction": "detailed instruction the user should follow",
      "success_criteria": "how to know this step is complete",
      "guidance_mode": "point_and_explain",
      "requires_screenshot_check": true,
      "can_user_mark_done": true,
      "fallback_hints": ["alternative way to find the button"]
    }
  ]
}
```

## Guidance Modes
- "point_and_explain": Show a pointer on screen at the target element
- "explain_only": Only describe what to do (no pointer) — use for conceptual steps

## Step Design Rules
1. Each step must be a SINGLE actionable instruction
2. Use specific UI element names (buttons, menus, tabs)
3. Include success criteria so the evaluator can verify completion
4. Provide fallback hints for when the exact element isn't found
5. Steps should be in logical order
6. Be conservative: 3-8 steps is usually enough

## Screen Context
You will receive a screenshot and optionally structured screen data.
Use it to plan, but ALWAYS prioritize the user's stated goal over what you see."""

# ── Template ──────────────────────────────────────────────────────────────────

PLANNER_TEMPLATE = """Goal: {goal}

Screen hints (what's visible on the user's screen):
{screen_hints}

Recent conversation:
{recent_messages}

Create a step-by-step plan to help the user accomplish their goal.
Return ONLY valid JSON."""


# ── Chain function ────────────────────────────────────────────────────────────


async def plan_goal(
    goal: str,
    images: List[Dict],
    session_snapshot: Optional[Dict] = None,
    settings: Any = None,
    signal: Any = None,
    screen_hints: str = "",
) -> Dict:
    """Generate a structured plan from a user goal.

    Maps to OpenGuider's planner-chain.js planGoal().

    Args:
        goal: The user's natural language goal
        images: List of screenshot dicts [{base64Jpeg, width, height}]
        session_snapshot: Optional session state for context
        settings: Config with LLM provider info
        signal: Optional cancellation signal
        screen_hints: Pre-formatted screen context text

    Returns:
        Dict with keys: goal, assistant_response, assumptions, steps (normalized)
    """
    logger.info(f"Planning goal: {goal[:80]}...")

    # Build recent messages context
    recent = "（新对话）"
    if session_snapshot and session_snapshot.get("messages"):
        msgs = session_snapshot["messages"][-6:]  # Last 6 messages
        recent = "\n".join(
            f"{m['role']}: {m['content'][:200]}" for m in msgs
            if m.get("role") and m.get("content")
        )

    try:
        result: PlannerOutput = await invoke_structured_chain(
            settings=settings,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            template=PLANNER_TEMPLATE,
            input_data={
                "goal": goal,
                "screen_hints": screen_hints or "（无屏幕信息）",
                "recent_messages": recent,
            },
            images=images,
            history=None,
            schema_class=PlannerOutput,
            signal=signal,
            operation_name="planner",
            is_locator=False,
            max_tokens=2048,
            temperature=0.3,
        )
    except Exception as e:
        logger.error(f"Planner failed: {e}")
        raise

    # Convert to dict for session normalization
    plan_dict = result.model_dump()
    plan_dict.setdefault("plan_id", "")
    plan_dict.setdefault("current_step_index", 0)
    plan_dict.setdefault("status", "pending_confirm")
    plan_dict.setdefault("created_at", "")
    plan_dict.setdefault("updated_at", "")

    # Normalize step statuses
    for i, step in enumerate(plan_dict.get("steps", [])):
        if isinstance(step, dict):
            step["status"] = "pending" if i > 0 else "active"
            step.setdefault("coordinate", None)
            step.setdefault("label", None)
            step.setdefault("explanation", "")
            step.setdefault("target_element_id", None)

    logger.info(
        f"Planner generated {len(plan_dict.get('steps', []))} steps"
    )
    return plan_dict
