"""
Task orchestrator — central coordinator for the PEER loop.

Python equivalent of OpenGuider's agent/task-orchestrator.js.

The orchestrator ties together all layers:
1. SessionManager (single source of truth)
2. InteractionPipeline (pre/post processing)
3. Chains (planner, executor, evaluator, replanner)
4. Core modules (trust manager, intent router)

Three operation modes:
- GUIDE: Default HITL mode. Plan → Guide → Evaluate → Repeat
- PLUGIN: Delegate to a plugin (browser, CLI)
- QUICK: Single-turn AI response, no plan (fallback)
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Status constants ──────────────────────────────────────────────────────────

STATUS_IDLE = "idle"
STATUS_PLANNING = "planning"
STATUS_EXECUTING = "executing"
STATUS_EVALUATING = "evaluating"
STATUS_WAITING_USER = "waiting_user"


class TaskOrchestrator:
    """Central task orchestrator — connects all layers.

    Maps to OpenGuider's agent/task-orchestrator.js TaskOrchestrator.

    Usage:
        orchestrator = TaskOrchestrator(
            session_manager=sm,
            interaction_pipeline=pipeline,
            capture_screen_fn=capture_fn,
        )
        result = await orchestrator.start_goal_session(text, images, settings)
    """

    def __init__(
        self,
        session_manager,
        interaction_pipeline,
        capture_screen_fn: Optional[Callable] = None,
    ):
        self.session = session_manager
        self.pipeline = interaction_pipeline
        self.capture_screen = capture_screen_fn or self._default_capture

        # Internal state
        self._active_plugin = None
        self._active_task_id = None
        self._active_trust_level = "balanced"
        self._abort_controller = None

        # Callbacks
        self.on_status_change: Optional[Callable] = None
        self.on_step_update: Optional[Callable] = None

    # ── Screenshot capture ──────────────────────────────────────────────────

    async def _default_capture(self, force_fresh: bool = False) -> List[Dict]:
        """Default screenshot capture (stub — should be overridden)."""
        logger.warning("Default capture called — no screenshots available")
        return []

    async def _resolve_screenshots(
        self,
        images: Optional[List[Dict]] = None,
        force_fresh: bool = False,
    ) -> List[Dict]:
        """Resolve screenshots from provided images or capture."""
        if images and len(images) > 0:
            self.session.set_last_screenshots(images)
            return images
        captured = await self.capture_screen(force_fresh=force_fresh)
        if captured:
            self.session.set_last_screenshots(captured)
        return captured or []

    # ── Goal session (entry point) ──────────────────────────────────────────

    async def start_goal_session(
        self,
        text: str,
        images: Optional[List[Dict]] = None,
        settings: Any = None,
        signal: Any = None,
    ) -> Dict:
        """Start a new goal session — the main entry point.

        Maps to OpenGuider's task-orchestrator.js startGoalSession().

        1. Route intent (guide vs plugin)
        2. If guide mode:
           a. Capture screenshots
           b. Run interaction pipeline preprocess
           c. Generate plan (planner chain)
           d. Guide first step (executor chain)
           e. Run postprocess
        3. If plugin mode:
           a. Delegate to plugin

        Args:
            text: User's natural language goal
            images: Optional pre-captured screenshots
            settings: LLM provider settings
            signal: Cancellation signal

        Returns:
            Dict with orchestrator result and session snapshot
        """
        logger.info(f"Starting goal session: {text[:80]}...")

        self.session.set_status(STATUS_PLANNING)
        self.session.add_message("user", text)

        # 1. Intent routing
        from core.intent_router import route

        route_result = await route(
            text=text,
            images=images,
            available_plugins=["browser"],
            settings=settings,
            signal=signal,
            use_llm=False,
        )

        # 2. Check for plugins
        if route_result.plugin_id and route_result.plugin_id != "guide":
            return await self._run_plugin_mode(
                text=text,
                route_result=route_result,
                settings=settings,
                signal=signal,
            )

        # 3. Guide mode: screenshots → plan → guide
        return await self._run_guide_mode(
            text=text,
            images=images,
            route_result=route_result,
            settings=settings,
            signal=signal,
        )

    # ── Guide mode ──────────────────────────────────────────────────────────

    async def _run_guide_mode(
        self,
        text: str,
        images: Optional[List[Dict]],
        route_result,
        settings: Any,
        signal: Any,
    ) -> Dict:
        """Execute in guide mode: Plan → Guide → Wait for user."""
        try:
            # Capture screenshots
            screenshots = await self._resolve_screenshots(images)

            # Preprocess
            pre_ctx = await self.pipeline.preprocess(
                images=screenshots,
                step=None,
                session_id=self.session.get_session().get("session_id", ""),
            )

            # Distill context
            enriched_prompt = await self.pipeline.distill_context(
                original_prompt=text,
                pre_context=pre_ctx,
                settings=settings,
            )

            # Build screen hints for planner
            from context.prompt_enricher import EnrichContext, build_enriched_prompt

            enrich_ctx = EnrichContext(
                ocr_result=pre_ctx.get("ocr_result"),
                window_info=pre_ctx.get("window_info"),
                matched_elements=pre_ctx.get("matched_elements", []),
            )
            screen_hints = build_enriched_prompt("", enrich_ctx, use_distilled=True)

            # Generate plan
            from agent.chains.planner_chain import plan_goal

            plan = await plan_goal(
                goal=text,
                images=screenshots,
                session_snapshot=self.session.get_snapshot(),
                settings=settings,
                signal=signal,
                screen_hints=screen_hints,
            )

            # Set plan in session
            self.session.set_active_plan(plan)
            self.session.set_status(STATUS_EXECUTING)
            self.session.add_message(
                "assistant",
                plan.get("assistant_response", "我已生成了操作计划。"),
            )

            # Guide the first step
            guide_result = await self.guide_current_step(
                settings=settings,
                user_note="",
                signal=signal,
                force_fresh_capture=False,
                force_pointing=False,
                pre_context=pre_ctx,
            )

            return {
                "mode": "guide",
                "plan": plan,
                "guide_result": guide_result,
                "session": self.session.get_snapshot(),
            }

        except Exception as e:
            logger.error(f"Guide mode error: {e}")
            # Fall back to single turn
            return await self.run_single_turn_fallback(
                text=text,
                images=images,
                settings=settings,
                signal=signal,
            )

    async def guide_current_step(
        self,
        settings: Any,
        user_note: str = "",
        signal: Any = None,
        force_fresh_capture: bool = False,
        force_pointing: bool = False,
        pre_context: Optional[Dict] = None,
    ) -> Dict:
        """Guide the user through the current plan step.

        Maps to OpenGuider's task-orchestrator.js guideCurrentStep().

        1. Get current step from plan
        2. Capture fresh screenshots
        3. Preprocess (OCR + windows)
        4. Locate target element (executor chain)
        5. Postprocess (validate + snap + verify)
        6. Set pointer in session
        """
        plan = self.session.get_active_plan()
        step = self.session.get_current_step()

        if not plan or not step:
            return {"error": "no active plan or step"}

        logger.info(f"Guiding step: {step.get('title', 'unknown')}")

        try:
            # Capture screenshots
            screenshots = await self._resolve_screenshots(
                force_fresh=force_fresh_capture,
            )

            # Preprocess (reuse if provided)
            if pre_context is None:
                pre_ctx = await self.pipeline.preprocess(
                    images=screenshots,
                    step=step,
                    session_id=self.session.get_session().get("session_id", ""),
                )
            else:
                pre_ctx = pre_context

            # Locate target
            from agent.chains.executor_chain import locate_step_target

            location = await locate_step_target(
                plan=plan,
                step=step,
                images=screenshots,
                settings=settings,
                user_note=user_note,
                signal=signal,
                force_pointing=force_pointing,
                preprocessing_context=pre_ctx,
            )

            # Postprocess
            post_result = await self.pipeline.postprocess(
                coordinate=location.get("coordinate"),
                label=location.get("label"),
                step=step,
                session_id=self.session.get_session().get("session_id", ""),
            )

            # Build pointer
            pointer = {
                "coordinate": post_result.get("coordinate"),
                "label": location.get("label"),
                "explanation": location.get("explanation", ""),
                "should_point": location.get("should_point", False),
                "confidence": post_result.get("confidence", 0.7),
                "verified": post_result.get("verified", False),
            }

            self.session.set_current_pointer(pointer)
            self.session.set_status(STATUS_WAITING_USER)

            # Build step message
            step_message = self._build_step_message(step, location, post_result)

            self.session.add_message("assistant", step_message)

            return {
                "step": step,
                "pointer": pointer,
                "location": location,
                "post_result": post_result,
                "message": step_message,
            }

        except Exception as e:
            logger.error(f"Guide step error: {e}")
            return {
                "error": str(e),
                "step": step,
                "message": f"无法定位目标元素：{str(e)[:100]}",
            }

    def _build_step_message(
        self,
        step: Dict,
        location: Dict,
        post_result: Dict,
    ) -> str:
        """Build a user-friendly step instruction message."""
        parts = [f"**{step.get('title', '')}**"]
        parts.append(step.get("instruction", ""))

        if location.get("should_point") and post_result.get("coordinate"):
            coord = post_result["coordinate"]
            conf = post_result.get("confidence", 0.7)
            parts.append(
                f"\n📍 目标位置已标记（置信度: {conf:.0%}）"
            )

        if location.get("explanation"):
            parts.append(f"\n💡 {location['explanation']}")

        return "\n".join(parts)

    # ── Step evaluation ─────────────────────────────────────────────────────

    async def evaluate_current_step(
        self,
        settings: Any,
        user_note: str = "",
        force_fresh_capture: bool = True,
        signal: Any = None,
    ) -> Dict:
        """Evaluate whether the user completed the current step.

        Maps to OpenGuider's task-orchestrator.js evaluateCurrentStep().
        """
        plan = self.session.get_active_plan()
        step = self.session.get_current_step()

        if not plan or not step:
            return {"error": "no active plan or step"}

        self.session.set_status(STATUS_EVALUATING)

        # Capture fresh screenshots
        screenshots = await self._resolve_screenshots(force_fresh=force_fresh_capture)

        from agent.chains.evaluator_chain import evaluate_step

        evaluation = await evaluate_step(
            plan=plan,
            step=step,
            images=screenshots,
            settings=settings,
            user_note=user_note,
            signal=signal,
        )

        self.session.append_evaluation(evaluation)
        self.session.add_message(
            "assistant",
            evaluation.get("assistant_response", ""),
        )

        return await self.handle_evaluation_result(
            evaluation=evaluation,
            settings=settings,
            signal=signal,
        )

    async def handle_evaluation_result(
        self,
        evaluation: Dict,
        settings: Any,
        signal: Any = None,
    ) -> Dict:
        """Route the evaluation result to the appropriate action.

        Maps to OpenGuider's task-orchestrator.js handleEvaluationResult().
        """
        status = evaluation.get("status", "uncertain")
        suggested_action = evaluation.get("suggested_action", "advance")

        if status == "done" or suggested_action == "advance":
            # Advance to next step
            updated_plan = self.session.complete_current_step()
            if updated_plan and updated_plan.get("status") == "completed":
                self.session.set_status(STATUS_IDLE)
                self.session.add_message(
                    "assistant",
                    "🎉 所有步骤已完成！",
                )
                return {
                    "action": "completed",
                    "evaluation": evaluation,
                    "session": self.session.get_snapshot(),
                }

            # Guide next step
            guide_result = await self.guide_current_step(
                settings=settings,
                signal=signal,
                force_fresh_capture=True,
            )
            return {
                "action": "advanced",
                "evaluation": evaluation,
                "guide_result": guide_result,
                "session": self.session.get_snapshot(),
            }

        elif suggested_action == "replan":
            return await self.replan_from_current(
                evaluation=evaluation,
                settings=settings,
                signal=signal,
            )

        else:  # repeat_guidance
            guide_result = await self.guide_current_step(
                settings=settings,
                signal=signal,
                force_fresh_capture=True,
                force_pointing=True,
            )
            return {
                "action": "repeated",
                "evaluation": evaluation,
                "guide_result": guide_result,
                "session": self.session.get_snapshot(),
            }

    async def replan_from_current(
        self,
        evaluation: Dict,
        settings: Any,
        signal: Any = None,
    ) -> Dict:
        """Replan from the current step when blocked."""
        plan = self.session.get_active_plan()
        step = self.session.get_current_step()

        if not plan or not step:
            return {"error": "no active plan or step"}

        screenshots = await self._resolve_screenshots(force_fresh=True)

        from agent.chains.replanner_chain import replan_goal

        replan_result = await replan_goal(
            plan=plan,
            step=step,
            evaluation=evaluation,
            images=screenshots,
            settings=settings,
            signal=signal,
        )

        self.session.set_active_plan(replan_result.get("plan"))
        self.session.add_message(
            "assistant",
            replan_result.get("assistant_response", "我已调整了计划。"),
        )

        # Guide first new step
        guide_result = await self.guide_current_step(
            settings=settings,
            signal=signal,
            force_fresh_capture=False,
        )

        return {
            "action": "replanned",
            "evaluation": evaluation,
            "replan_result": replan_result,
            "guide_result": guide_result,
            "session": self.session.get_snapshot(),
        }

    # ── User step actions ───────────────────────────────────────────────────

    async def mark_step_done(
        self,
        settings: Any,
        signal: Any = None,
    ) -> Dict:
        """User marks current step as done — evaluate and advance."""
        return await self.evaluate_current_step(
            settings=settings,
            user_note="用户标记此步骤完成",
            signal=signal,
        )

    async def skip_current_step(self) -> Dict:
        """Skip the current step."""
        result = self.session.skip_current_step()
        if result is None:
            return {"error": "no active plan"}
        self.session.set_status(STATUS_EXECUTING)
        return {"action": "skipped", "session": self.session.get_snapshot()}

    async def previous_step(self) -> Dict:
        """Go back to the previous step."""
        result = self.session.go_to_previous_step()
        if result is None:
            return {"error": "no active plan"}
        self.session.set_status(STATUS_EXECUTING)
        return {"action": "previous", "session": self.session.get_snapshot()}

    async def regenerate_current_step(
        self,
        settings: Any,
        signal: Any = None,
    ) -> Dict:
        """Re-guide the current step with forced pointing."""
        return await self.guide_current_step(
            settings=settings,
            signal=signal,
            force_fresh_capture=True,
            force_pointing=True,
        )

    async def request_step_help(
        self,
        settings: Any,
        signal: Any = None,
    ) -> Dict:
        """Request additional help for the current step."""
        return await self.guide_current_step(
            settings=settings,
            user_note="需要更详细的指导",
            signal=signal,
            force_fresh_capture=True,
            force_pointing=True,
        )

    async def recheck_current_step(
        self,
        settings: Any,
        signal: Any = None,
    ) -> Dict:
        """Re-check the current step (replan from scratch)."""
        plan = self.session.get_active_plan()
        step = self.session.get_current_step()

        if not plan or not step:
            return {"error": "no active plan"}

        screenshots = await self._resolve_screenshots(force_fresh=True)

        pre_ctx = await self.pipeline.preprocess(
            images=screenshots,
            step=step,
            session_id=self.session.get_session().get("session_id", ""),
        )

        from context.prompt_enricher import EnrichContext, build_enriched_prompt

        enrich_ctx = EnrichContext(
            ocr_result=pre_ctx.get("ocr_result"),
            window_info=pre_ctx.get("window_info"),
            matched_elements=pre_ctx.get("matched_elements", []),
        )
        screen_hints = build_enriched_prompt("", enrich_ctx, use_distilled=True)

        from agent.chains.planner_chain import plan_goal

        new_plan = await plan_goal(
            goal=plan.get("goal", ""),
            images=screenshots,
            session_snapshot=self.session.get_snapshot(),
            settings=settings,
            signal=signal,
            screen_hints=screen_hints,
        )

        self.session.set_active_plan(new_plan)
        self.session.set_status(STATUS_EXECUTING)

        return await self.guide_current_step(
            settings=settings,
            signal=signal,
            force_fresh_capture=False,
            pre_context=pre_ctx,
        )

    def cancel_active_plan(self, silent: bool = False) -> Dict:
        """Cancel the current plan."""
        self.session.set_active_plan(None)
        self.session.set_status(STATUS_IDLE)
        if not silent:
            self.session.add_message(
                "assistant",
                "已取消当前任务。有什么我可以帮你的吗？",
            )
        self.pipeline.clear()
        return {"action": "cancelled", "session": self.session.get_snapshot()}

    # ── Plugin mode ─────────────────────────────────────────────────────────

    async def _run_plugin_mode(
        self,
        text: str,
        route_result,
        settings: Any,
        signal: Any,
    ) -> Dict:
        """Execute via a plugin (browser, CLI)."""
        logger.info(f"Plugin mode: {route_result.plugin_id}")
        return {
            "mode": "plugin",
            "plugin_id": route_result.plugin_id,
            "goal": route_result.goal,
            "trust": route_result.trust,
            "message": f"Plugin '{route_result.plugin_id}' not yet implemented.",
            "session": self.session.get_snapshot(),
        }

    # ── Single turn fallback ────────────────────────────────────────────────

    async def run_single_turn_fallback(
        self,
        text: str,
        images: Optional[List[Dict]] = None,
        settings: Any = None,
        signal: Any = None,
    ) -> Dict:
        """Run a single-turn AI response when planning fails.

        Maps to OpenGuider's task-orchestrator.js runSingleTurnFallback().
        """
        logger.info("Running single-turn fallback")

        screenshots = await self._resolve_screenshots(images)

        pre_ctx = await self.pipeline.preprocess(
            images=screenshots,
            step=None,
            session_id=self.session.get_session().get("session_id", ""),
        )

        enriched = await self.pipeline.distill_context(
            original_prompt=text,
            pre_context=pre_ctx,
            settings=settings,
        )

        try:
            from server_v2.services.llm.client import call_llm

            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful desktop assistant. Answer the user's question concisely.",
                },
                {"role": "user", "content": enriched},
            ]

            response = await call_llm(
                messages=messages,
                settings=settings,
                max_tokens=1024,
                temperature=0.7,
            )

            self.session.add_message("assistant", response)
            self.session.set_status(STATUS_IDLE)

            return {
                "mode": "quick",
                "response": response,
                "session": self.session.get_snapshot(),
            }

        except Exception as e:
            logger.error(f"Single-turn fallback failed: {e}")
            return {
                "mode": "quick",
                "error": str(e),
                "session": self.session.get_snapshot(),
            }

    # ── Helpers ─────────────────────────────────────────────────────────────

    def get_snapshot(self) -> Dict:
        """Get current session snapshot."""
        return self.session.get_snapshot()

    def reset_session(self) -> Dict:
        """Reset to fresh session."""
        self.pipeline.clear()
        self.session.clear_session()
        return self.session.get_snapshot()

    def set_aware_assistance(self, enabled: bool) -> None:
        """Enable/disable the interaction pipeline."""
        self.pipeline.set_enabled(enabled)
