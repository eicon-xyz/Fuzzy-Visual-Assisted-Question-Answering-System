"""
HAJIMI 自动操作助手 — 执行引擎

主循环：Plan → SafetyCheck → Execute → Verify → Next/Replan
SSE 事件通过 thread-safe queue 推送给 /stream 端点。
"""

from __future__ import annotations

import logging
import queue
import threading
import time

from server.services.memory.extractor import MemoryExtractor

logger = logging.getLogger(__name__)

# 全局事件队列：{task_id: queue.Queue}
_event_queues: dict[str, queue.Queue] = {}
_queues_lock = threading.Lock()
_cancel_flags: dict[str, bool] = {}
_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()


def _push_event(task_id: str, event: str, data: dict) -> None:
    """推送一个 SSE 事件到对应任务的事件队列。"""
    with _queues_lock:
        q = _event_queues.get(task_id)
    if q:
        q.put({"event": event, "data": data})


def _is_cancelled(task_id: str) -> bool:
    """检查任务是否已被取消。"""
    with _cancel_lock:
        return _cancel_flags.get(task_id, False)


# ═══════════════════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════════════════


def register_task(task_id: str) -> queue.Queue:
    """注册新任务，返回其事件队列供 /stream 端点消费。"""
    with _queues_lock:
        existing = _event_queues.get(task_id)
        if existing is not None:
            logger.info(f"[engine] task {task_id} already registered, reusing queue")
            return existing
        q: queue.Queue = queue.Queue()
        _event_queues[task_id] = q
    with _cancel_lock:
        _cancel_flags[task_id] = False
        _cancel_events[task_id] = threading.Event()
    logger.info(f"[engine] registered task {task_id}")
    return q


def cancel_task(task_id: str) -> bool:
    """取消任务。"""
    with _cancel_lock:
        event = _cancel_events.get(task_id)
        if event:
            event.set()
            logger.info(f"[engine] cancel event set for {task_id}")
            _cancel_flags[task_id] = True
            return True
    # Fallback to old boolean cancel flag for backward compat
    with _cancel_lock:
        if task_id in _cancel_flags:
            _cancel_flags[task_id] = True
            logger.info(f"[engine] cancel flag set for {task_id} (legacy)")
            return True
    return False


def get_cancel_event(task_id: str) -> threading.Event:
    """获取任务的取消 Event，不存在时返回一个已清除的 Event。"""
    with _cancel_lock:
        return _cancel_events.get(task_id, threading.Event())


def unregister_task(task_id: str) -> None:
    """清理任务资源。"""
    with _queues_lock:
        _event_queues.pop(task_id, None)
    with _cancel_lock:
        _cancel_events.pop(task_id, None)
        _cancel_flags.pop(task_id, None)
    logger.info(f"[engine] unregistered task {task_id}")


def _trigger_memory_extraction_success(
    goal: str,
    steps: list[dict],
    previous_steps: list[dict],
) -> None:
    """Fire-and-forget: extract success memory in background thread."""
    def _extract():
        try:
            extractor = MemoryExtractor()
            extractor.extract_from_success(
                user_id="default",
                user_query=goal,
                steps=steps,
            )
        except Exception:
            logger.exception("Background memory extraction failed")

    threading.Thread(target=_extract, daemon=True).start()


def _trigger_memory_extraction_failure(
    goal: str,
    steps: list[dict],
    failed_step_idx: int,
) -> None:
    """Fire-and-forget: extract failure memory in background thread.

    Only triggered when the entire task failed (all retries exhausted).
    """
    def _extract():
        try:
            # Build error detail
            failed_step = steps[failed_step_idx - 1] if failed_step_idx <= len(steps) else {}
            error_detail = f"Step {failed_step_idx} failed: {failed_step.get('instruction', 'unknown')}"
            extractor = MemoryExtractor()
            extractor.extract_from_failure(
                user_id="default",
                user_query=goal,
                steps=steps,
                error_detail=error_detail,
            )
        except Exception:
            logger.exception("Background failure memory extraction failed")

    threading.Thread(target=_extract, daemon=True).start()


def run_plan_agent_loop(
    task_id: str,
    goal: str,
    steps: list[dict],
    cancel_event: threading.Event,
) -> None:
    """
    Execute a plan using the Execution Agent loop.
    Pushes SSE events for real-time observability.

    Args:
        task_id: Task identifier
        goal: Overall task goal from Planning Agent
        steps: List of step dicts [{step_index, instruction, ...}]
        cancel_event: Set by /cancel endpoint
    """
    from server.models.schemas import ExecutedStep
    from server.services.executor.agent import ExecutionAgent

    register_task(task_id)
    agent = ExecutionAgent()
    previous_steps: list[dict] = []
    all_done = True

    from server.config import settings

    retry_limit = getattr(settings, "STEP_RETRY_LIMIT", 1)

    for step_dict in steps:
        if cancel_event.is_set():
            _push_event(task_id, "task_cancelled", {})
            all_done = False
            break

        step_idx = step_dict["step_index"]
        instruction = step_dict["instruction"]

        _push_event(
            task_id,
            "step_start",
            {
                "step_index": step_idx,
                "instruction": instruction,
            },
        )

        # Build ExecutedStep
        es = ExecutedStep(
            step_index=step_idx,
            instruction=instruction,
            status="executing",
        )

        # Run agent loop for this step
        try:
            result = agent.execute_step(
                step=es,
                goal=goal,
                previous_steps=previous_steps,
                task_id=task_id,
                cancel_event=cancel_event,
                on_screenshot=lambda b64: _push_event(
                    task_id,
                    "screenshot_updated",
                    {"step_index": step_idx, "annotated_image": b64},
                ),
            )
        except Exception as e:
            logger.exception(f"Step {step_idx} execution crashed")
            result = ExecutedStep(
                step_index=step_idx,
                instruction=instruction,
                status="failed",
                action_summary=f"crash: {e}",
            )

        if result.status == "done":
            _push_event(
                task_id,
                "step_done",
                {
                    "step_index": step_idx,
                    "action_summary": result.action_summary or "",
                },
            )
            previous_steps.append(
                {
                    "index": step_idx,
                    "instruction": instruction,
                    "status": "done",
                    "action_summary": result.action_summary or "completed",
                }
            )
        else:
            # Retry loop (STEP_RETRY_LIMIT times)
            retry_success = False
            for retry_attempt in range(retry_limit):
                if cancel_event and cancel_event.is_set():
                    _push_event(task_id, "task_cancelled", {})
                    all_done = False  # signal task was cancelled
                    return  # exit the thread, task cancelled
                logger.warning(
                    f"Step {step_idx} failed, retry {retry_attempt+1}/{retry_limit}..."
                )
                _push_event(
                    task_id,
                    "log",
                    {
                        "level": "warn",
                        "message": f"步骤 {step_idx} 失败，重试 {retry_attempt+1}/{retry_limit}...",
                    },
                )
                try:
                    agent.clear_element_map()
                    retry_result = agent.execute_step(
                        step=es,
                        goal=goal,
                        previous_steps=previous_steps,
                        task_id=task_id,
                        cancel_event=cancel_event,
                    )
                    if retry_result.status == "done":
                        _push_event(
                            task_id,
                            "step_done",
                            {
                                "step_index": step_idx,
                                "action_summary": retry_result.action_summary or "",
                            },
                        )
                        previous_steps.append(
                            {
                                "index": step_idx,
                                "instruction": instruction,
                                "status": "done",
                                "action_summary": retry_result.action_summary
                                or "completed (retry)",
                            }
                        )
                        retry_success = True
                        break
                except Exception:
                    logger.exception(f"Step {step_idx} retry {retry_attempt+1} crashed")

            if not retry_success:
                _push_event(
                    task_id,
                    "step_failed",
                    {
                        "step_index": step_idx,
                        "reason": result.action_summary or "step failed after retries",
                    },
                )
                all_done = False
                break

    if all_done:
        _push_event(
            task_id,
            "task_done",
            {
                "task_id": task_id,
                "goal": goal,
                "total_steps": len(steps),
                "completed_steps": len(previous_steps),
            },
        )
        # Trigger async memory extraction (fire-and-forget)
        _trigger_memory_extraction_success(goal, steps, previous_steps)
    else:
        _push_event(
            task_id,
            "task_failed",
            {
                "reason": "step execution failed or cancelled",
                "failed_step": len(previous_steps) + 1,
            },
        )
        # Trigger failure memory extraction (fire-and-forget)
        failed_step_idx = len(previous_steps) + 1
        _trigger_memory_extraction_failure(goal, steps, failed_step_idx)

    # Delayed cleanup
    def _cleanup():
        time.sleep(3)
        try:
            agent.close_browser()
        except Exception:
            pass
        unregister_task(task_id)

    threading.Thread(target=_cleanup, daemon=True).start()


# ── Legacy alias for backward compat ──
run_plan = run_plan_agent_loop
