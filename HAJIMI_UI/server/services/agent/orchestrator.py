"""
HAJIMI_UI — Task Orchestrator (sync)

Transplanted from OpenSource hajimi-og-v2/server/services/agent/orchestrator.py.
Matches OpenGuider's src/agent/task-orchestrator.js.

Process flow: plan_and_locate → (user acts) → evaluate_step → advance/replan
Pure vision LLM pipeline — no OmniParser dependency.
"""
from __future__ import annotations
import logging
from typing import Optional

from server.services.session.manager import session_manager
from server.services.agent.chains import (
    plan_and_locate, plan_goal, locate_step_target,
    evaluate_step, replan_goal, fast_mode_chat,
)
from server.services.llm.providers import parse_point_tags
from server.services.validation.postprocess import postprocess_pointer

logger = logging.getLogger(__name__)


class TaskOrchestrator:
    """Central orchestrator. Matches OpenGuider's TaskOrchestrator class.

    Manages the full lifecycle:
      process_query → plan+locate → (user acts) → evaluate → advance/replan
    """

    def __init__(self):
        self._session = session_manager
        self._provider: str | None = None

    def set_provider(self, provider: str):
        self._provider = provider

    @property
    def session(self):
        return self._session

    # ═══════════════════════════════════════════════════════════════════════
    # process_query — uses combo plan+locate (ONE LLM call, not two)
    # ═══════════════════════════════════════════════════════════════════════

    def process_query(
        self,
        query: str,
        image_base64: Optional[str] = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> dict:
        """Main entry. Uses plan_and_locate() for single-LLM-call performance.

        Args:
            query: User's natural language task description
            image_base64: Base64 screenshot (optional)
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels

        Returns:
            {
                "success": bool,
                "reply": str,           # Assistant message to user
                "plan": dict | None,    # {goal, steps[], currentStepIndex}
                "pointer": dict | None, # {x, y, label, scaledX, scaledY}
                "session": dict,
            }
        """
        self._session.set_status("planning")
        self._session.add_message("user", query)

        session_msgs = self._session.get_messages()
        history_dicts = [{"role": m["role"], "content": m["content"]} for m in session_msgs]

        # Single LLM call: plan + locate in one request
        logger.info(f"plan+locate: {query[:80]}...")
        try:
            combo = plan_and_locate(
                goal=query,
                image_base64=image_base64,
                session_messages=history_dicts,
                provider=self._provider,
                screen_width=screen_width,
                screen_height=screen_height,
            )
        except Exception as e:
            logger.error(f"plan+locate failed: {e}, falling back to fast chat")
            try:
                reply = fast_mode_chat(
                    text=query,
                    image_base64=image_base64,
                    provider=self._provider,
                )
            except Exception:
                reply = f"I encountered an error: {e}"
            self._session.add_message("assistant", reply)
            self._session.set_status("idle")
            return {
                "success": False,
                "reply": reply,
                "plan": None,
                "pointer": None,
                "session": self._session.get_snapshot(),
            }

        steps = combo["steps"]
        if not steps:
            reply = combo.get("assistantResponse", "I couldn't create a plan for that.")
            self._session.add_message("assistant", reply)
            self._session.set_status("idle")
            return {
                "success": True,
                "reply": reply,
                "plan": None,
                "pointer": None,
                "session": self._session.get_snapshot(),
            }

        # Set step statuses: first active, rest pending
        steps[0]["status"] = "active"
        for s in steps[1:]:
            s["status"] = "pending"

        plan = {
            "goal": combo["goal"],
            "current_step_index": 0,
            "steps": steps,
            "status": "active",
        }
        self._session.set_active_plan(plan)

        pointer = combo["pointer"]
        first_step = steps[0]

        # Use the combo's natural-language assistantResponse as the chat message
        msg = combo.get("assistantResponse", first_step.get("instruction", ""))
        self._session.add_message("assistant", msg)
        self._session.set_last_pointer(pointer)
        self._session.set_status("waiting_user")

        # Compute absolute coords for overlay + run post-processing
        coords = None
        if pointer.get("x") is not None and pointer.get("y") is not None:
            result = postprocess_pointer(
                float(pointer["x"]), float(pointer["y"]),
                label=pointer.get("label", "element"),
                screen_w=screen_width, screen_h=screen_height,
            )
            coords = {
                "x": result["x"], "y": result["y"],
                "scaledX": result["scaledX"], "scaledY": result["scaledY"],
            }

        return {
            "success": True,
            "reply": msg,
            "plan": {
                "goal": plan["goal"],
                "steps": [
                    {
                        "stepIndex": i + 1,
                        "title": s.get("title", f"Step {i + 1}"),
                        "instruction": s.get("instruction", ""),
                        "successCriteria": s.get("successCriteria", ""),
                        "guidanceMode": s.get("guidanceMode", "point_and_explain"),
                        "status": s.get("status", "pending"),
                    }
                    for i, s in enumerate(steps)
                ],
                "currentStepIndex": 0,
            },
            "pointer": {
                "x": pointer.get("x"),
                "y": pointer.get("y"),
                "label": pointer.get("label", "element"),
                "explanation": pointer.get("explanation", ""),
                "scaledX": coords["x"] if coords else None,
                "scaledY": coords["y"] if coords else None,
            },
            "session": self._session.get_snapshot(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # evaluate_current_step
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_current_step(
        self,
        image_base64: Optional[str] = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> dict:
        """Evaluate whether the current step is done, then advance or replan.

        Returns: {action, evaluation, session}
        """
        plan = self._session.get_active_plan()
        step = self._session.get_current_step()
        if not plan or not step:
            return {
                "action": "no_plan",
                "session": self._session.get_snapshot(),
            }

        self._session.set_status("evaluating")
        evaluation = evaluate_step(
            goal=plan.get("goal", ""),
            step=step,
            image_base64=image_base64,
            provider=self._provider,
        )
        self._session.add_evaluation(evaluation)

        action = evaluation.get("suggestedAction", "repeat_guidance")

        if action == "advance" or evaluation.get("status") == "done":
            self._session.complete_current_step()
            next_step = self._session.get_current_step()
            if next_step:
                # Locate the next step's target
                try:
                    pointer = locate_step_target(
                        goal=plan.get("goal", ""),
                        step=next_step,
                        image_base64=image_base64,
                        step_number=plan.get("current_step_index", 0) + 1,
                        total_steps=len(plan.get("steps", [])),
                        force_point=True,
                        provider=self._provider,
                    )
                    self._session.set_last_pointer(pointer)

                    # Post-process coordinates
                    if pointer.get("x") is not None and pointer.get("y") is not None:
                        result = postprocess_pointer(
                            float(pointer["x"]), float(pointer["y"]),
                            label=pointer.get("label", "element"),
                            screen_w=screen_width, screen_h=screen_height,
                        )
                        pointer["scaledX"] = result["x"]
                        pointer["scaledY"] = result["y"]

                    msg = pointer.get("explanation") or next_step.get("instruction", "")
                    self._session.add_message("assistant", msg)
                except Exception as e:
                    logger.warning(f"Locate next step failed: {e}")
                    self._session.add_message(
                        "assistant",
                        next_step.get("instruction", "Proceed to the next step."),
                    )
            self._session.set_status("waiting_user" if next_step else "idle")

        elif action == "replan" or evaluation.get("status") == "blocked":
            # Replan blocked step
            try:
                new_plan_data = replan_goal(
                    goal=plan.get("goal", ""),
                    failed_step_title=step.get("title", ""),
                    rationale=evaluation.get("rationale", ""),
                    image_base64=image_base64,
                    provider=self._provider,
                )
                if new_plan_data.get("steps"):
                    new_steps = new_plan_data["steps"]
                    new_steps[0]["status"] = "active"
                    for s in new_steps[1:]:
                        s["status"] = "pending"
                    self._session.set_active_plan({
                        "goal": new_plan_data.get("goal", plan.get("goal", "")),
                        "current_step_index": 0,
                        "steps": new_steps,
                        "status": "active",
                    })
                    self._session.add_message(
                        "assistant",
                        new_plan_data.get("assistantResponse", "Let me adjust the plan."),
                    )
                    self._session.set_status("waiting_user")
                else:
                    self._session.set_status("idle")
            except Exception as e:
                logger.error(f"Replan failed: {e}")
                self._session.set_status("idle")
        else:
            # repeat_guidance or uncertain — stay on current step
            self._session.set_status("waiting_user")

        return {
            "action": action,
            "evaluation": evaluation,
            "session": self._session.get_snapshot(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # Step actions
    # ═══════════════════════════════════════════════════════════════════════

    def mark_step_done(self) -> dict:
        self._session.complete_current_step()
        return {"session": self._session.get_snapshot()}

    def skip_step(self) -> dict:
        self._session.skip_current_step()
        return {"session": self._session.get_snapshot()}

    def previous_step(self) -> dict:
        self._session.go_to_previous_step()
        return {"session": self._session.get_snapshot()}

    def cancel_plan(self) -> dict:
        self._session.reset()
        return {"session": self._session.get_snapshot()}

    def request_step_help(
        self,
        image_base64: Optional[str] = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> dict:
        """Re-locate the current step's target element."""
        plan = self._session.get_active_plan()
        step = self._session.get_current_step()
        if not plan or not step:
            return {"session": self._session.get_snapshot()}

        try:
            pointer = locate_step_target(
                goal=plan.get("goal", ""),
                step=step,
                image_base64=image_base64,
                step_number=plan.get("current_step_index", 0) + 1,
                total_steps=len(plan.get("steps", [])),
                force_point=True,
                provider=self._provider,
            )
            self._session.set_last_pointer(pointer)

            if pointer.get("x") is not None and pointer.get("y") is not None:
                result = postprocess_pointer(
                    float(pointer["x"]), float(pointer["y"]),
                    label=pointer.get("label", "element"),
                    screen_w=screen_width, screen_h=screen_height,
                )
                pointer["scaledX"] = result["x"]
                pointer["scaledY"] = result["y"]

            self._session.add_message("assistant", pointer.get("explanation") or step.get("instruction", ""))
        except Exception as e:
            logger.error(f"Step help failed: {e}")

        return {"session": self._session.get_snapshot()}

    # ═══════════════════════════════════════════════════════════════════════
    # Fast Mode — simple chat without plan
    # ═══════════════════════════════════════════════════════════════════════

    def send_message(
        self,
        text: str,
        image_base64: Optional[str] = None,
        history: list | None = None,
    ) -> dict:
        """Simple chat message, no plan generation."""
        self._session.add_message("user", text)
        self._session.set_status("thinking")

        full_text = fast_mode_chat(
            text=text,
            image_base64=image_base64,
            history=history,
            provider=self._provider,
        )
        parsed = parse_point_tags(full_text)
        self._session.add_message("assistant", parsed["spokenText"] or full_text)
        self._session.set_status("idle")

        result = {
            "spokenText": parsed["spokenText"] or full_text,
            "session": self._session.get_snapshot(),
        }
        if parsed.get("coordinate"):
            result["coordinate"] = parsed["coordinate"]
            result["label"] = parsed["label"]
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════

    def get_session(self) -> dict:
        return self._session.get_snapshot()

    def reset_session(self):
        self._session.reset()


# Global singleton
orchestrator = TaskOrchestrator()
