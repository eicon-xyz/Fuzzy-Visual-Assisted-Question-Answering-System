"""
HAJIMI_UI — Agent Chains (sync)

Matches OpenGuider's planner-chain.js, executor-chain.js, evaluator-chain.js, replanner-chain.js.
Uses pure vision LLM — screenshots go directly to multimodal LLM, no OmniParser needed.
"""

from __future__ import annotations

import logging
from typing import Optional

from server.services.agent.prompts import (
    EVALUATOR_SYSTEM_PROMPT,
    EVALUATOR_USER_TEMPLATE,
    LOCATOR_SYSTEM_PROMPT,
    LOCATOR_USER_TEMPLATE,
    PLAN_LOCATE_COMBO_SYSTEM,
    PLAN_LOCATE_COMBO_USER,
    PLANNER_SYSTEM_PROMPT,
    PLANNER_USER_TEMPLATE,
    REPLANNER_SYSTEM_PROMPT,
    REPLANNER_USER_TEMPLATE,
    STRICT_LOCATOR_SYSTEM_PROMPT,
)
from server.services.llm.providers import (
    DEFAULT_SYSTEM_PROMPT,
    call_llm,
    call_llm_json,
    extract_json_object,
    parse_point_tags,
)
from server.services.memory.retriever import get_retriever

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _summarize_screenshots(images: list | None = None) -> str:
    if not images:
        return "No screenshot attached."
    lines = []
    for i, img in enumerate(images):
        lbl = img.get("label", f"Screen {i + 1}")
        w = img.get("width", "?")
        h = img.get("height", "?")
        lines.append(f"Screen {i + 1}: {lbl} ({w}x{h})")
    return "\n".join(lines)


def _build_step_dicts(raw_steps: list[dict], start_index: int = 0) -> list[dict]:
    """Normalize raw step dicts from LLM into standard format."""
    steps = []
    for s in raw_steps:
        if isinstance(s, str):
            steps.append(
                {
                    "id": f"step_{len(steps) + start_index}",
                    "title": s[:40],
                    "instruction": s,
                    "successCriteria": s,
                    "guidanceMode": "point_and_explain",
                    "requiresScreenshotCheck": True,
                    "canUserMarkDone": True,
                    "fallbackHints": [],
                    "status": "pending",
                }
            )
        else:
            steps.append(
                {
                    "id": s.get("id", f"step_{len(steps) + start_index}"),
                    "title": s.get("title", "Step"),
                    "instruction": s.get("instruction", ""),
                    "successCriteria": s.get(
                        "successCriteria", s.get("instruction", "")
                    ),
                    "guidanceMode": s.get("guidanceMode", "point_and_explain"),
                    "requiresScreenshotCheck": s.get("requiresScreenshotCheck", True),
                    "canUserMarkDone": s.get("canUserMarkDone", True),
                    "fallbackHints": s.get("fallbackHints", []),
                    "status": "pending",
                }
            )
    return steps


# ═══════════════════════════════════════════════════════════════════════════
# Combo: Plan + Locate in ONE call (cuts latency in half)
# ═══════════════════════════════════════════════════════════════════════════


def plan_and_locate(
    goal: str,
    image_base64: Optional[str] = None,
    session_messages: list | None = None,
    provider: str | None = None,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> dict:
    """One LLM call that returns both plan steps AND first step's pointer coordinates.

    This is the KEY innovation: OpenGuider does plan + locate as 2 calls;
    we combine them into 1, cutting latency in half.

    Args:
        goal: User's goal/task description
        image_base64: Base64 screenshot (optional but recommended)
        session_messages: Recent conversation messages
        provider: LLM provider name
        screen_width: Screen width for context (default 1920)
        screen_height: Screen height for context (default 1080)

    Returns:
        {
            "goal": str,
            "assistantResponse": str,
            "assumptions": list[str],
            "steps": list[dict],   # {id, title, instruction, successCriteria, ...}
            "pointer": {           # First step's pointer
                "x": float, "y": float,      # 0-1000 normalized
                "label": str,
                "explanation": str,
                "shouldPoint": bool,
            }
        }
    """
    recent = (session_messages or [])[-6:]
    recent_text = (
        "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in recent)
        or "No earlier messages."
    )

    images = None
    if image_base64:
        images = [{"base64Jpeg": image_base64, "label": "Screen"}]

    screen_hints = _summarize_screenshots(images)

    # Retrieve user memories for prompt injection
    user_memory = ""
    try:
        retriever = get_retriever()
        user_memory = retriever.retrieve(
            user_id="default",  # Phase 1: single-user, use default
            query=goal,
            element_count=None,  # No element count available in planner
        )
    except Exception:
        pass  # Memory retrieval failure should not block planning

    user_text = PLAN_LOCATE_COMBO_USER.format(
        goal=goal,
        recentMessages=recent_text,
        screenHints=screen_hints,
        user_memory=user_memory,
    )

    # Get raw text via LLM
    raw = call_llm(
        user_text=user_text,
        images=images,
        system_prompt=PLAN_LOCATE_COMBO_SYSTEM,
        provider=provider,
        temperature=0.3,
        max_tokens=4096,
        timeout=120,
    )

    data = extract_json_object(raw)

    # Build step list
    steps = _build_step_dicts(data.get("steps", []))

    # Extract pointer from combo response
    pointer_data = data.get("pointer", {})
    coord_x = pointer_data.get("x")
    coord_y = pointer_data.get("y")
    should_point = pointer_data.get("shouldPoint", True)

    # Also try to harvest [POINT] from assistantResponse
    if coord_x is None or coord_y is None:
        assist_text = data.get("assistantResponse", "")
        parsed = parse_point_tags(assist_text)
        if parsed.get("coordinate"):
            coord_x = int(parsed["coordinate"]["x"])
            coord_y = int(parsed["coordinate"]["y"])
            should_point = True

    # Build pointer object
    pointer = {
        "x": coord_x,
        "y": coord_y,
        "label": pointer_data.get(
            "label", data.get("assistantResponse", "element")[:30]
        ),
        "explanation": data.get("assistantResponse", ""),
        "shouldPoint": should_point and coord_x is not None,
    }

    return {
        "goal": data.get("goal", goal),
        "assistantResponse": data.get("assistantResponse", f"I'll help you {goal}."),
        "assumptions": data.get("assumptions", []),
        "steps": steps,
        "pointer": pointer,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Planner (standalone) — matches planGoal() in planner-chain.js
# ═══════════════════════════════════════════════════════════════════════════


def plan_goal(
    goal: str,
    image_base64: Optional[str] = None,
    session_messages: list | None = None,
    provider: str | None = None,
) -> dict:
    """Create a plan from goal + screenshot. Returns {goal, assistantResponse, assumptions, steps}."""
    recent = (session_messages or [])[-6:]
    recent_text = (
        "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in recent)
        or "No earlier messages."
    )

    images = None
    if image_base64:
        images = [{"base64Jpeg": image_base64, "label": "Screen"}]

    screen_hints = _summarize_screenshots(images)

    user_memory = ""
    try:
        retriever = get_retriever()
        user_memory = retriever.retrieve(
            user_id="default",
            query=goal,
        )
    except Exception:
        pass

    user_text = PLANNER_USER_TEMPLATE.format(
        goal=goal,
        recentMessages=recent_text,
        screenHints=screen_hints,
        user_memory=user_memory,
    )

    data = call_llm_json(
        user_text=user_text,
        images=images,
        system_prompt=PLANNER_SYSTEM_PROMPT,
        provider=provider,
        temperature=0.3,
        max_tokens=4096,
        timeout=120,
    )

    steps = _build_step_dicts(data.get("steps", []))
    return {
        "goal": data.get("goal", goal),
        "assistantResponse": data.get("assistantResponse", f"I'll help you {goal}."),
        "assumptions": data.get("assumptions", []),
        "steps": steps,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Locator — matches locateStepTarget() in executor-chain.js
# ═══════════════════════════════════════════════════════════════════════════


def locate_step_target(
    goal: str,
    step: dict,
    image_base64: Optional[str] = None,
    step_number: int = 1,
    total_steps: int = 1,
    force_point: bool = False,
    provider: str | None = None,
) -> dict:
    """Locate a specific step's target element on screen.

    Returns: {x, y, label, explanation, shouldPoint} (0-1000 normalized coords)
    """
    images = None
    if image_base64:
        images = [{"base64Jpeg": image_base64, "label": "Screen"}]

    user_text = LOCATOR_USER_TEMPLATE.format(
        goal=goal,
        stepTitle=step.get("title", "Step"),
        instruction=step.get("instruction", ""),
    )

    parsed = call_llm_json(
        user_text=user_text,
        images=images,
        system_prompt=LOCATOR_SYSTEM_PROMPT,
        provider=provider,
        temperature=0.2,
        max_tokens=2048,
        timeout=60,
        is_locator=True,
    )

    coord_data = parsed.get("coordinate")
    coord_x = None
    coord_y = None
    if coord_data and isinstance(coord_data, dict):
        coord_x = coord_data.get("x")
        coord_y = coord_data.get("y")

    should_point = bool(parsed.get("shouldPoint", coord_x is not None))

    # Strict retry if force_point and no coordinate found
    if force_point and (coord_x is None or coord_y is None) and image_base64:
        logger.info("Strict locator retry for step: %s", step.get("title"))
        parsed2 = call_llm_json(
            user_text=user_text,
            images=images,
            system_prompt=STRICT_LOCATOR_SYSTEM_PROMPT,
            provider=provider,
            temperature=0.1,
            max_tokens=2048,
            timeout=60,
            is_locator=True,
        )
        cd2 = parsed2.get("coordinate")
        if cd2 and isinstance(cd2, dict):
            coord_x = cd2.get("x")
            coord_y = cd2.get("y")
            should_point = True

    return {
        "x": coord_x,
        "y": coord_y,
        "label": parsed.get("label") or step.get("title", "element"),
        "explanation": parsed.get("explanation", ""),
        "shouldPoint": should_point,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Evaluator — matches evaluateStep() in evaluator-chain.js
# ═══════════════════════════════════════════════════════════════════════════

EVALUATOR_ENABLED = True  # Toggle via settings


def evaluate_step(
    goal: str,
    step: dict,
    image_base64: Optional[str] = None,
    provider: str | None = None,
) -> dict:
    """Evaluate whether the current step has been completed.

    Args:
        goal: Overall task goal
        step: Current step dict {title, instruction, successCriteria}
        image_base64: New screenshot to evaluate against
        provider: LLM provider

    Returns:
        {status: "done"|"not_done"|"blocked"|"uncertain",
         confidence: float,
         rationale: str,
         suggestedAction: "advance"|"repeat_guidance"|"replan",
         assistantResponse: str}
    """
    if not EVALUATOR_ENABLED:
        return {
            "status": "done",
            "confidence": 1.0,
            "rationale": "Evaluator disabled, auto-advancing.",
            "suggestedAction": "advance",
            "assistantResponse": "",
        }

    images = None
    if image_base64:
        images = [{"base64Jpeg": image_base64, "label": "Screen"}]

    user_text = EVALUATOR_USER_TEMPLATE.format(
        goal=goal,
        stepTitle=step.get("title", "Step"),
        instruction=step.get("instruction", ""),
        successCriteria=step.get("successCriteria", step.get("instruction", "")),
    )

    try:
        data = call_llm_json(
            user_text=user_text,
            images=images,
            system_prompt=EVALUATOR_SYSTEM_PROMPT,
            provider=provider,
            temperature=0.2,
            max_tokens=2048,
            timeout=60,
        )
        return {
            "status": data.get("status", "not_done"),
            "confidence": float(data.get("confidence", 0.5)),
            "rationale": data.get("rationale", ""),
            "suggestedAction": data.get("suggestedAction", "repeat_guidance"),
            "assistantResponse": data.get("assistantResponse", ""),
        }
    except Exception as e:
        logger.warning(f"Evaluate step failed: {e}, defaulting to advance")
        return {
            "status": "done",
            "confidence": 0.5,
            "rationale": f"Evaluation error: {e}",
            "suggestedAction": "advance",
            "assistantResponse": "",
        }


# ═══════════════════════════════════════════════════════════════════════════
# Replanner — matches replanGoal() in replanner-chain.js
# ═══════════════════════════════════════════════════════════════════════════


def replan_goal(
    goal: str,
    failed_step_title: str = "",
    rationale: str = "",
    image_base64: Optional[str] = None,
    provider: str | None = None,
) -> dict:
    """Create a revised plan when the current one is blocked.

    Returns: {goal, assistantResponse, assumptions, steps}
    """
    images = None
    if image_base64:
        images = [{"base64Jpeg": image_base64, "label": "Screen"}]

    user_text = REPLANNER_USER_TEMPLATE.format(
        goal=goal,
        failedStepTitle=failed_step_title,
        rationale=rationale,
    )

    data = call_llm_json(
        user_text=user_text,
        images=images,
        system_prompt=REPLANNER_SYSTEM_PROMPT,
        provider=provider,
        temperature=0.3,
        max_tokens=4096,
        timeout=120,
    )

    steps = _build_step_dicts(data.get("steps", []))
    return {
        "goal": data.get("goal", goal),
        "assistantResponse": data.get("assistantResponse", "Let me adjust the plan."),
        "assumptions": data.get("assumptions", []),
        "steps": steps,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Fast Mode Chat — bypass plan, just chat with screen context
# ═══════════════════════════════════════════════════════════════════════════


def fast_mode_chat(
    text: str,
    image_base64: Optional[str] = None,
    history: list | None = None,
    provider: str | None = None,
) -> str:
    """Simple chat with optional screen context. No plan generation."""
    images = None
    if image_base64:
        images = [{"base64Jpeg": image_base64, "label": "Screen"}]

    return call_llm(
        user_text=text,
        images=images,
        history=history,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        provider=provider,
        temperature=0.7,
        max_tokens=4096,
        timeout=120,
    )
