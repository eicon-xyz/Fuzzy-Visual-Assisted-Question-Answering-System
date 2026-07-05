"""
HAJIMI_UI — Session Manager

Mirrors OpenGuider's src/session/session-manager.js.
State machine for task session state.
"""
from __future__ import annotations
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """Centralized session state machine.

    Mirrors OpenGuider's SessionManager EventEmitter class.
    """

    def __init__(self, session_id: str = "default"):
        self._session_id = session_id
        self._messages: list[dict] = []
        self._status: str = "idle"
        self._active_plan: Optional[dict] = None  # {goal, steps[], current_step_index, status}
        self._last_pointer: Optional[dict] = None  # {x, y, label, explanation}
        self._evaluation_history: list[dict] = []
        self._last_screenshots: list = []

    # ── Snapshot ──────────────────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        return {
            "sessionId": self._session_id,
            "messages": list(self._messages),
            "status": self._status,
            "activePlan": self._active_plan,
            "lastPointer": self._last_pointer,
            "evaluationHistory": list(self._evaluation_history),
            "updatedAt": str(time.time()),
        }

    # ── Messages ──────────────────────────────────────────────────────────

    def add_message(self, role: str, content: str):
        self._messages.append({"role": role, "content": content})
        # Keep last 80 messages max
        if len(self._messages) > 80:
            self._messages = self._messages[-80:]

    def get_messages(self) -> list[dict]:
        return list(self._messages)

    def clear_messages(self):
        self._messages = []

    # ── Status ────────────────────────────────────────────────────────────

    def set_status(self, status: str):
        self._status = status

    def get_status(self) -> str:
        return self._status

    # ── Active Plan ───────────────────────────────────────────────────────

    def set_active_plan(self, plan: dict | None):
        self._active_plan = plan

    def get_active_plan(self) -> Optional[dict]:
        return self._active_plan

    def get_current_step(self) -> Optional[dict]:
        if not self._active_plan or not self._active_plan.get("steps"):
            return None
        idx = self._active_plan.get("current_step_index", 0)
        steps = self._active_plan["steps"]
        if 0 <= idx < len(steps):
            return steps[idx]
        return None

    def get_current_step_index(self) -> int:
        if not self._active_plan:
            return 0
        return self._active_plan.get("current_step_index", 0)

    def complete_current_step(self):
        """Mark current step completed and advance."""
        if not self._active_plan:
            return
        idx = self._active_plan.get("current_step_index", 0)
        steps = self._active_plan.get("steps", [])
        if 0 <= idx < len(steps):
            steps[idx]["status"] = "completed"
        next_idx = idx + 1
        if next_idx >= len(steps):
            self._active_plan["status"] = "completed"
            self._status = "idle"
        else:
            self._active_plan["current_step_index"] = next_idx
            if next_idx < len(steps):
                steps[next_idx]["status"] = "active"
            self._status = "waiting_user"

    def go_to_previous_step(self):
        """Retreat one step."""
        if not self._active_plan:
            return
        idx = self._active_plan.get("current_step_index", 0)
        steps = self._active_plan.get("steps", [])
        if idx > 0:
            if 0 <= idx < len(steps):
                steps[idx]["status"] = "pending"
            self._active_plan["current_step_index"] = idx - 1
            if idx - 1 < len(steps):
                steps[idx - 1]["status"] = "active"
            self._status = "waiting_user"

    def skip_current_step(self):
        """Skip current step and advance."""
        if not self._active_plan:
            return
        idx = self._active_plan.get("current_step_index", 0)
        steps = self._active_plan.get("steps", [])
        if 0 <= idx < len(steps):
            steps[idx]["status"] = "skipped"
        next_idx = idx + 1
        if next_idx >= len(steps):
            self._active_plan["status"] = "completed"
            self._status = "idle"
        else:
            self._active_plan["current_step_index"] = next_idx
            if next_idx < len(steps):
                steps[next_idx]["status"] = "active"
            self._status = "waiting_user"

    # ── Pointer ───────────────────────────────────────────────────────────

    def set_last_pointer(self, pointer: dict | None):
        self._last_pointer = pointer

    def get_last_pointer(self) -> Optional[dict]:
        return self._last_pointer

    # ── Evaluations ───────────────────────────────────────────────────────

    def add_evaluation(self, eval_result: dict):
        self._evaluation_history.append(eval_result)
        if len(self._evaluation_history) > 40:
            self._evaluation_history = self._evaluation_history[-40:]

    # ── Screenshots ───────────────────────────────────────────────────────

    def set_last_screenshots(self, screenshots: list):
        self._last_screenshots = screenshots

    # ── Reset ─────────────────────────────────────────────────────────────

    def reset(self):
        """Full session reset."""
        from server.services.validation.postprocess import reset_history
        self._messages = []
        self._status = "idle"
        self._active_plan = None
        self._last_pointer = None
        self._evaluation_history = []
        self._last_screenshots = []
        reset_history()


# Global singleton
session_manager = SessionManager()
