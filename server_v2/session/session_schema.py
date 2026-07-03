"""
Session schema normalization functions.

Python equivalent of OpenGuider's session/session-schema.js.
Ensures consistent plan/step/execution structures across modules.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any


# ── Session creation ─────────────────────────────────────────────────────────


def create_empty_session() -> dict:
    """Create a fresh empty session state.

    Maps to OpenGuider's session-schema.js createEmptySession().
    """
    return {
        "session_id": str(uuid.uuid4()),
        "messages": [],
        "goal_intent": "",
        "active_plan": None,
        "browser_execution": None,
        "current_step_id": None,
        "manual_confirmation": False,
        "last_screenshots": [],
        "evaluation_history": [],
        "status": "idle",  # idle|planning|executing|evaluating|waiting_user
        "last_pointer": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


# ── Plan normalization ───────────────────────────────────────────────────────


def normalize_plan(plan_dict: dict, existing_steps: Optional[List[dict]] = None) -> dict:
    """Normalize a plan dict from the planner chain output.

    Maps to OpenGuider's session-schema.js normalizePlan().

    Ensures every step has all required fields and correct statuses.
    """
    plan_id = plan_dict.get("plan_id") or str(uuid.uuid4())[:8]
    now = _now_iso()

    steps = []
    for i, step in enumerate(plan_dict.get("steps", [])):
        normalized_step = normalize_step(step)
        # Set status based on position
        if existing_steps and i < len(existing_steps):
            normalized_step["status"] = existing_steps[i].get("status", "pending")
        elif i == 0:
            normalized_step["status"] = "active"
        else:
            normalized_step["status"] = "pending"
        steps.append(normalized_step)

    return {
        "plan_id": plan_id,
        "goal": plan_dict.get("goal", ""),
        "assumptions": plan_dict.get("assumptions", []),
        "steps": steps,
        "current_step_index": plan_dict.get("current_step_index", 0),
        "total_steps": len(steps),
        "status": plan_dict.get("status", "pending_confirm"),
        "created_at": plan_dict.get("created_at", now),
        "updated_at": now,
    }


def normalize_step(step: dict) -> dict:
    """Normalize a single step with all required fields.

    Maps to OpenGuider's session-schema.js cloneStep().
    """
    return {
        "id": step.get("id", f"step_{step.get('step_index', '?')}"),
        "title": step.get("title", ""),
        "instruction": step.get("instruction", step.get("title", "")),
        "success_criteria": step.get("success_criteria", ""),
        "guidance_mode": step.get("guidance_mode", "point_and_explain"),
        "requires_screenshot_check": step.get("requires_screenshot_check", True),
        "can_user_mark_done": step.get("can_user_mark_done", True),
        "fallback_hints": step.get("fallback_hints", []),
        "status": step.get("status", "pending"),  # pending|active|completed|skipped
        "coordinate": step.get("coordinate", None),
        "label": step.get("label", None),
        "explanation": step.get("explanation", ""),
        "target_element_id": step.get("target_element_id", None),
        "annotation": step.get("annotation", None),
        "risk_score": step.get("risk_score", 2),
    }


def get_current_step(plan: Optional[dict]) -> Optional[dict]:
    """Get the currently active step from a normalized plan.

    Maps to OpenGuider's session-schema.js getCurrentStep().
    """
    if not plan:
        return None
    steps = plan.get("steps", [])
    idx = plan.get("current_step_index", 0)
    if 0 <= idx < len(steps):
        return steps[idx]
    return None


# ── Browser execution normalization ──────────────────────────────────────────


def normalize_browser_execution(execution: Optional[dict]) -> Optional[dict]:
    """Normalize browser execution state."""
    if not execution:
        return None
    return {
        "task_id": execution.get("task_id", ""),
        "plugin_id": execution.get("plugin_id", ""),
        "goal": execution.get("goal", ""),
        "substeps": execution.get("substeps", []),
        "status": execution.get("status", "idle"),
        "started_at": execution.get("started_at", _now_iso()),
    }


def normalize_browser_substep(substep: dict) -> dict:
    """Normalize a browser execution substep."""
    return {
        "step_number": substep.get("step_number", 0),
        "action_type": substep.get("action_type", ""),
        "action": substep.get("action", ""),
        "description": substep.get("description", ""),
        "screenshot_before": substep.get("screenshot_before", None),
        "screenshot_after": substep.get("screenshot_after", None),
        "risk_score": substep.get("risk_score", 3),
        "status": substep.get("status", "pending"),
        "started_at": substep.get("started_at", None),
        "completed_at": substep.get("completed_at", None),
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
