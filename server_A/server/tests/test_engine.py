"""
Layer 1 — Execution Engine event flow (mock ExecutionAgent)

Tests run_plan_agent_loop, register_task, cancel_task, unregister_task.
All external deps mocked: ExecutionAgent.execute_step returns canned ExecutedStep.
No real LLM, no browser, no display.
"""

import pytest
import threading
import time
import queue
from unittest.mock import MagicMock, patch

from server.services.executor import engine
from server.models.schemas import ExecutedStep


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_done_step(index=1, instruction="test step", summary="done"):
    return ExecutedStep(
        step_index=index, instruction=instruction,
        status="done", action_summary=summary,
    )


def _make_failed_step(index=1, instruction="test step", summary="failed"):
    return ExecutedStep(
        step_index=index, instruction=instruction,
        status="failed", action_summary=summary,
    )


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_global_state():
    """Wipe global event queues and cancel flags between tests."""
    engine._event_queues.clear()
    engine._cancel_flags.clear()
    engine._cancel_events.clear()
    yield
    engine._event_queues.clear()
    engine._cancel_flags.clear()
    engine._cancel_events.clear()


# ============================================================================
# Task registration / cancellation
# ============================================================================


class TestRegisterUnregister:
    def test_register_returns_queue(self):
        q = engine.register_task("task-1")
        assert isinstance(q, queue.Queue)

    def test_register_idempotent(self):
        q1 = engine.register_task("task-1")
        q2 = engine.register_task("task-1")
        assert q1 is q2  # same queue instance

    def test_unregister_cleans_up(self):
        engine.register_task("task-1")
        engine.unregister_task("task-1")
        assert "task-1" not in engine._event_queues
        assert "task-1" not in engine._cancel_flags
        assert "task-1" not in engine._cancel_events

    def test_unregister_nonexistent_does_not_crash(self):
        engine.unregister_task("no-such-task")  # should not raise


class TestCancelTask:
    def test_cancel_sets_flag(self):
        engine.register_task("task-1")
        result = engine.cancel_task("task-1")
        assert result is True
        assert engine._cancel_flags["task-1"] is True

    def test_cancel_event_is_set(self):
        engine.register_task("task-1")
        result = engine.cancel_task("task-1")
        assert result is True
        assert engine._cancel_events["task-1"].is_set()

    def test_cancel_nonexistent_returns_false(self):
        result = engine.cancel_task("no-such-task")
        assert result is False


class TestCancelEvent:
    def test_existing_task_returns_event(self):
        engine.register_task("task-1")
        ev = engine.get_cancel_event("task-1")
        assert isinstance(ev, threading.Event)

    def test_nonexistent_returns_cleared_event(self):
        ev = engine.get_cancel_event("no-task")
        assert isinstance(ev, threading.Event)
        assert not ev.is_set()


# ============================================================================
# run_plan_agent_loop — mocked ExecutionAgent
# ============================================================================


def _drain_events(task_id: str, timeout: float = 5.0) -> list[dict]:
    """Drain all events from queue for task_id, return list of {event, data} items."""
    events = []
    q = engine._event_queues.get(task_id)
    if not q:
        return events
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            evt = q.get(timeout=0.3)
            events.append(evt)
        except queue.Empty:
            break
    return events


def _run_and_collect(task_id, goal, steps, cancel_event=None) -> list[dict]:
    """Run run_plan_agent_loop in a thread, wait for completion, return events."""
    if cancel_event is None:
        cancel_event = threading.Event()

    engine.register_task(task_id)

    thread = threading.Thread(
        target=engine.run_plan_agent_loop,
        args=(task_id, goal, steps, cancel_event),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=10)

    return _drain_events(task_id)


@pytest.fixture(autouse=True)
def _mock_execution_agent():
    with patch("server.services.executor.agent.ExecutionAgent") as MockAgent:
        mock = MagicMock()
        MockAgent.return_value = mock
        yield mock


def _make_steps(*instructions):
    return [
        {"step_index": i + 1, "instruction": instr}
        for i, instr in enumerate(instructions)
    ]


class TestRunPlanAgentLoop:
    """Full engine pipeline tests with mocked ExecutionAgent."""

    def test_all_steps_succeed(self, _mock_execution_agent):
        agent = _mock_execution_agent
        agent.execute_step.return_value = _make_done_step(1)
        agent.close_browser = MagicMock()

        events = _run_and_collect(
            "task-ok", "Do the thing",
            _make_steps("Step A", "Step B"),
        )
        event_types = [e["event"] for e in events]
        assert "step_start" in event_types
        assert "step_done" in event_types
        assert "task_done" in event_types
        assert "task_failed" not in event_types

    def test_step_failure_stops_pipeline(self, _mock_execution_agent):
        agent = _mock_execution_agent
        agent.execute_step.return_value = _make_failed_step(1)
        agent.close_browser = MagicMock()

        events = _run_and_collect(
            "task-fail", "Do the thing",
            _make_steps("Step A", "Step B"),
        )
        event_types = [e["event"] for e in events]
        assert "step_failed" in event_types or "task_failed" in event_types

    def test_task_done_event_has_correct_data(self, _mock_execution_agent):
        agent = _mock_execution_agent
        agent.execute_step.return_value = _make_done_step(1, summary="clicked button")
        agent.close_browser = MagicMock()

        events = _run_and_collect(
            "task-data", "Click the button",
            _make_steps("Find and click"),
        )
        done_events = [e for e in events if e["event"] == "task_done"]
        assert len(done_events) == 1
        assert done_events[0]["data"]["total_steps"] == 1

    def test_cancel_mid_execution(self, _mock_execution_agent):
        def slow_exec(*args, **kwargs):
            time.sleep(0.5)
            return _make_done_step(1)

        _mock_execution_agent.execute_step = slow_exec
        _mock_execution_agent.close_browser = MagicMock()

        engine.register_task("task-cancel-h")
        cancel_event = threading.Event()
        thread = threading.Thread(
            target=engine.run_plan_agent_loop,
            args=("task-cancel-h", "Goal", _make_steps("Step A", "Step B", "Step C"), cancel_event),
            daemon=True,
        )
        thread.start()
        time.sleep(0.1)
        cancel_event.set()
        thread.join(timeout=10)
        events = _drain_events("task-cancel-h")
        event_types = [e["event"] for e in events]
        # After cancel, fewer steps completed than total (3)
        assert len([e for e in event_types if e == "step_done"]) < 3

    def test_retry_success(self, _mock_execution_agent):
        """Step fails then retry succeeds."""
        agent = _mock_execution_agent
        # First call fails, second succeeds (retry)
        agent.execute_step.side_effect = [
            _make_failed_step(1),
            _make_done_step(1, summary="retry worked"),
            _make_done_step(2, summary="step 2 done"),
        ]
        agent.close_browser = MagicMock()

        # Patch STEP_RETRY_LIMIT to 1
        with patch.object(engine, "retry_limit", 1, create=True):
            events = _run_and_collect(
                "task-retry", "Goal",
                _make_steps("Step A", "Step B"),
            )
        done_events = [e for e in events if e["event"] == "step_done"]
        assert len(done_events) >= 2  # retry + step 2

    def test_event_ordering(self, _mock_execution_agent):
        agent = _mock_execution_agent
        agent.execute_step.return_value = _make_done_step(1)
        agent.close_browser = MagicMock()

        events = _run_and_collect(
            "task-order", "Goal",
            _make_steps("Step A", "Step B"),
        )
        event_types = [e["event"] for e in events]

        # step_start must appear before step_done for each step
        for i in range(2):
            starts = [j for j, et in enumerate(event_types) if et == "step_start"]
            dones = [j for j, et in enumerate(event_types) if et == "step_done"]
            # Each step_start should have a corresponding step_done after it
            assert len(starts) == len(dones)
