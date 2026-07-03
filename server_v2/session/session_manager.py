"""Session manager — single source of truth for task state.

Python equivalent of OpenGuider's session/session-manager.js.

The SessionManager is the authoritative state container for all
task-related state. It emits update callbacks on every mutation,
enabling reactive UI updates and consistent state across modules.

Note: Coexists with TaskStore (database persistence layer).
SessionManager = real-time memory state
TaskStore = durable DB records
"""

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .session_schema import (
    create_empty_session,
    normalize_plan,
    normalize_step,
    get_current_step,
)

logger = logging.getLogger(__name__)

# Status constants
STATUS_IDLE = "idle"
STATUS_PLANNING = "planning"
STATUS_EXECUTING = "executing"
STATUS_EVALUATING = "evaluating"
STATUS_WAITING_USER = "waiting_user"


class SessionManager:
    """Central session state container with observer pattern.

    Maps to OpenGuider's session-manager.js SessionManager.

    Usage:
        sm = SessionManager()
        sm.on_update(lambda snapshot: broadcast(snapshot))
        sm.set_status("planning")
        sm.set_active_plan(plan_dict)
        step = sm.get_current_step()
    """

    def __init__(self):
        self._state = create_empty_session()
        self._on_update_callbacks: List[Callable] = []

    # ── Observer pattern ────────────────────────────────────────────────────

    def on_update(self, callback: Callable[[dict], None]) -> None:
        """Register a callback to be called on every state mutation."""
        self._on_update_callbacks.append(callback)

    def _emit(self) -> None:
        """Notify all observers with a deep snapshot."""
        snapshot = self.get_snapshot()
        for cb in self._on_update_callbacks:
            try:
                cb(snapshot)
            except Exception as e:
                logger.error(f"Session update callback error: {e}")

    def _touch(self) -> None:
        self._state["updated_at"] = datetime.now(timezone.utc).isoformat()

    # ── Snapshot ────────────────────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """Get a deep copy of current session state."""
        return copy.deepcopy(self._state)

    def get_session(self) -> dict:
        """Get the raw session state (not a copy — use carefully)."""
        return self._state

    # ── Status ──────────────────────────────────────────────────────────────

    def set_status(self, status: str) -> None:
        """Set session status (idle, planning, executing, evaluating, waiting_user)."""
        old = self._state["status"]
        self._state["status"] = status
        self._touch()
        if old != status:
            logger.debug(f"Session status: {old} -> {status}")
        self._emit()

    def get_status(self) -> str:
        return self._state["status"]

    # ── Goal / Intent ───────────────────────────────────────────────────────

    def set_goal_intent(self, text: str) -> None:
        self._state["goal_intent"] = text
        self._touch()
        self._emit()

    # ── Messages ────────────────────────────────────────────────────────────

    def add_message(self, role: str, content: str) -> None:
        """Add a chat message to the session."""
        self._state["messages"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Trim to last 80 messages
        if len(self._state["messages"]) > 80:
            self._state["messages"] = self._state["messages"][-80:]
        self._touch()
        self._emit()

    def set_messages(self, messages: List[dict]) -> None:
        self._state["messages"] = list(messages)
        self._touch()
        self._emit()

    def get_recent_messages(self, count: int = 6) -> List[dict]:
        """Get the most recent N messages."""
        return self._state["messages"][-count:]

    # ── Active plan ─────────────────────────────────────────────────────────

    def set_active_plan(self, plan: Optional[dict]) -> None:
        """Set the active plan (normalized)."""
        if plan:
            self._state["active_plan"] = normalize_plan(plan)
            self._state["current_step_id"] = (
                self._state["active_plan"]["steps"][0]["id"]
                if self._state["active_plan"].get("steps")
                else None
            )
        else:
            self._state["active_plan"] = None
            self._state["current_step_id"] = None
        self._touch()
        self._emit()

    def get_active_plan(self) -> Optional[dict]:
        return self._state.get("active_plan")

    def get_current_step(self) -> Optional[dict]:
        """Get the currently active step."""
        return get_current_step(self._state.get("active_plan"))

    def update_active_plan(self, mutator: Callable[[dict], dict]) -> None:
        """Apply a mutation function to the active plan."""
        plan = self._state.get("active_plan")
        if plan:
            self._state["active_plan"] = mutator(plan)
            self._touch()
            self._emit()

    # ── Step transitions ────────────────────────────────────────────────────

    def complete_current_step(self) -> Optional[dict]:
        """Mark current step as completed and advance to next.

        Returns the updated plan, or None if no more steps.
        """
        plan = self._state.get("active_plan")
        if not plan:
            return None

        steps = plan.get("steps", [])
        idx = plan.get("current_step_index", 0)

        if idx >= len(steps):
            return None

        # Mark current as completed
        steps[idx]["status"] = "completed"

        # Advance
        next_idx = idx + 1
        if next_idx < len(steps):
            steps[next_idx]["status"] = "active"
            plan["current_step_index"] = next_idx
            self._state["current_step_id"] = steps[next_idx]["id"]
            plan["status"] = "executing"
        else:
            # All steps done
            plan["current_step_index"] = next_idx
            plan["status"] = "completed"
            self._state["current_step_id"] = None

        self._touch()
        self._emit()
        return plan

    def go_to_previous_step(self) -> Optional[dict]:
        """Go back to the previous step."""
        plan = self._state.get("active_plan")
        if not plan:
            return None

        steps = plan.get("steps", [])
        idx = plan.get("current_step_index", 0)

        if idx <= 0:
            return plan

        # Mark current as pending
        if idx < len(steps):
            steps[idx]["status"] = "pending"

        # Go back
        prev_idx = idx - 1
        steps[prev_idx]["status"] = "active"
        plan["current_step_index"] = prev_idx
        self._state["current_step_id"] = steps[prev_idx]["id"]
        plan["status"] = "executing"

        self._touch()
        self._emit()
        return plan

    def skip_current_step(self) -> Optional[dict]:
        """Skip the current step without completing it."""
        plan = self._state.get("active_plan")
        if not plan:
            return None

        steps = plan.get("steps", [])
        idx = plan.get("current_step_index", 0)

        if idx >= len(steps):
            return None

        steps[idx]["status"] = "skipped"

        next_idx = idx + 1
        if next_idx < len(steps):
            steps[next_idx]["status"] = "active"
            plan["current_step_index"] = next_idx
            self._state["current_step_id"] = steps[next_idx]["id"]
        else:
            plan["status"] = "completed"
            self._state["current_step_id"] = None

        self._touch()
        self._emit()
        return plan

    # ── Pointer ─────────────────────────────────────────────────────────────

    def set_current_pointer(self, pointer: Optional[dict]) -> None:
        """Set the current screen pointer coordinate + label."""
        self._state["last_pointer"] = pointer
        # Also update in active step
        plan = self._state.get("active_plan")
        if plan and pointer:
            step = get_current_step(plan)
            if step:
                step["coordinate"] = pointer.get("coordinate")
                step["label"] = pointer.get("label")
                step["explanation"] = pointer.get("explanation", "")
        self._touch()
        self._emit()

    # ── Screenshots ─────────────────────────────────────────────────────────

    def set_last_screenshots(self, screenshots: List[dict]) -> None:
        """Store the most recent screenshots (without base64 for memory)."""
        # Strip base64 from stored screenshots to save memory
        light = []
        for s in screenshots:
            light.append({
                k: v for k, v in s.items()
                if k != "base64Jpeg"
            })
        self._state["last_screenshots"] = light
        self._touch()

    # ── Evaluation ──────────────────────────────────────────────────────────

    def append_evaluation(self, evaluation: dict) -> None:
        """Append an evaluation result to history."""
        evaluation["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._state["evaluation_history"].append(evaluation)
        # Trim to last 40
        if len(self._state["evaluation_history"]) > 40:
            self._state["evaluation_history"] = self._state["evaluation_history"][-40:]
        self._touch()
        self._emit()

    # ── Browser execution ───────────────────────────────────────────────────

    def set_browser_execution(self, execution: Optional[dict]) -> None:
        self._state["browser_execution"] = execution
        self._touch()
        self._emit()

    def clear_browser_execution(self) -> None:
        self._state["browser_execution"] = None
        self._touch()
        self._emit()

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def clear_session(self) -> None:
        """Reset to empty session."""
        self._state = create_empty_session()
        self._emit()
        logger.info("Session cleared")

    def hydrate_session(self, snapshot: dict) -> None:
        """Restore session from a persisted snapshot."""
        required = create_empty_session()
        for key in required:
            if key in snapshot:
                self._state[key] = snapshot[key]
        self._touch()
        self._emit()
        logger.info("Session hydrated from snapshot")
