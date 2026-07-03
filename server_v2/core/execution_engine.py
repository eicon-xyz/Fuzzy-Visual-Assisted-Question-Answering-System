"""
HITL (Human-in-the-Loop) execution engine for plugin step processing.

Python equivalent of OpenGuider's core/execution-engine.js.

Wraps AsyncStepQueue with trust-based auto-approval logic for
plugin-driven step execution (browser automation, CLI, etc.).
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from .trust_manager import should_auto_approve, validate_trust_level
from .step_queue import AsyncStepQueue

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Step execution engine with HITL approval.

    Maps to OpenGuider's core/execution-engine.js ExecutionEngine.

    For each step:
    1. Get risk score from plugin
    2. Check trust manager for auto-approval
    3. If manual approval needed, emit event and wait for user decision
    4. Execute the step via plugin
    5. Emit result

    Usage:
        engine = ExecutionEngine(plugin, trust_level="balanced", task_id="task_1")
        engine.on_step_pending = lambda step: print("Waiting for approval...")
        engine.enqueue_step(step)
        await engine.drain()
    """

    def __init__(
        self,
        plugin: Any = None,
        trust_level: str = "balanced",
        task_id: str = "",
    ):
        self._plugin = plugin
        self._trust_level = validate_trust_level(trust_level)
        self._task_id = task_id
        self._queue = AsyncStepQueue(processor=self._process_one_step)
        self._decision_event = asyncio.Event()
        self._current_decision: Optional[dict] = None
        self._decision_timeout = 120  # seconds

        # Callbacks
        self.on_step_pending: Optional[Callable] = None
        self.on_step_complete: Optional[Callable] = None
        self.on_step_error: Optional[Callable] = None

    # ── Queue ───────────────────────────────────────────────────────────────

    def enqueue_step(self, step: Any) -> None:
        """Enqueue a step for execution."""
        self._queue.enqueue(step)

    def pause(self) -> None:
        self._queue.pause()

    def resume(self) -> None:
        self._queue.resume()

    async def abort(self) -> None:
        self._queue.abort()
        if self._plugin and hasattr(self._plugin, "abort"):
            try:
                await self._plugin.abort()
            except Exception as e:
                logger.error(f"Plugin abort error: {e}")

    async def drain(self) -> None:
        await self._queue.drain()

    # ── Processing ──────────────────────────────────────────────────────────

    async def _process_one_step(self, step: Any) -> dict:
        """Process a single step with HITL approval check.

        Returns:
            dict with {step_id, success, message, requires_human_review}
        """
        step_id = getattr(step, "id", None) or str(step)

        # 1. Get risk score
        risk_score = 3
        if self._plugin and hasattr(self._plugin, "get_risk_score"):
            try:
                risk_score = self._plugin.get_risk_score(step)
            except Exception:
                pass

        # 2. Get step description
        description = str(step)
        if self._plugin and hasattr(self._plugin, "describe_step"):
            try:
                description = self._plugin.describe_step(step)
            except Exception:
                pass

        # 3. Check auto-approval
        plugin_requires_review = (
            getattr(step, "requires_human_review", False)
            or getattr(step, "context", {}).get("requires_human_review", False)
        )

        auto_approved = should_auto_approve(
            risk_score=risk_score,
            trust_level=self._trust_level,
            plugin_requires_review=plugin_requires_review,
        )

        decision = "continue" if auto_approved else "pending"

        # 4. If not auto-approved, wait for user
        if not auto_approved:
            decision = await self._await_user_decision(step, description, risk_score)

        # 5. Execute based on decision
        if decision == "abort":
            return {
                "step_id": step_id,
                "success": False,
                "message": "User aborted",
                "requires_human_review": False,
            }

        if decision == "skip":
            return {
                "step_id": step_id,
                "success": True,
                "message": "User skipped",
                "requires_human_review": False,
            }

        # decision == "continue" or "approve"
        try:
            if self._plugin and hasattr(self._plugin, "execute_step"):
                result = await self._plugin.execute_step(step)
                if self.on_step_complete:
                    self.on_step_complete(step, result)
                return result
            else:
                return {
                    "step_id": step_id,
                    "success": True,
                    "message": "No plugin executor — step marked as done",
                    "requires_human_review": False,
                }
        except Exception as e:
            logger.error(f"Step execution error: {e}")
            if self.on_step_error:
                self.on_step_error(step, e)
            return {
                "step_id": step_id,
                "success": False,
                "message": str(e),
                "error": str(e),
                "requires_human_review": False,
            }

    async def _await_user_decision(
        self,
        step: Any,
        description: str,
        risk_score: int,
    ) -> str:
        """Wait for user decision on a pending step.

        Returns 'continue', 'skip', 'replan', or 'abort'.
        """
        self._decision_event.clear()
        self._current_decision = {
            "step": step,
            "description": description,
            "risk_score": risk_score,
        }

        # Emit pending event
        if self.on_step_pending:
            try:
                self.on_step_pending(self._current_decision)
            except Exception as e:
                logger.error(f"on_step_pending error: {e}")

        # Wait for decision or timeout
        try:
            await asyncio.wait_for(
                self._decision_event.wait(),
                timeout=self._decision_timeout,
            )
            # Decision was set via resolve_decision()
            decision_data = self._current_decision or {}
            return decision_data.get("decision", "continue")
        except asyncio.TimeoutError:
            logger.warning(
                f"User decision timeout ({self._decision_timeout}s). Auto-skipping."
            )
            return "skip"

    def resolve_decision(self, decision: str) -> None:
        """Resolve a pending user decision.

        Args:
            decision: 'continue', 'skip', 'replan', or 'abort'
        """
        if self._current_decision:
            self._current_decision["decision"] = decision
        self._decision_event.set()
        logger.debug(f"User decision resolved: {decision}")

    # ── Trust level ─────────────────────────────────────────────────────────

    def set_trust_override(self, new_level: str) -> None:
        """Change the trust level mid-execution."""
        self._trust_level = validate_trust_level(new_level)
        logger.info(f"Trust level changed to: {self._trust_level}")
