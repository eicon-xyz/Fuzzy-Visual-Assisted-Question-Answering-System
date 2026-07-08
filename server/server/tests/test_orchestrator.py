"""
Layer 1 — TaskOrchestrator state machine (mock all LLM chains)

Tests process_query and evaluate_current_step with mocked LLM chains.
All LLM chain functions are mocked — no real LLM calls.
fresh_session fixture provides isolated state per test.
"""

import pytest
from unittest.mock import patch

from server.services.agent.orchestrator import TaskOrchestrator


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_plan(goal="Test task", steps_count=3):
    return {
        "goal": goal,
        "assistantResponse": "Let me help you.",
        "assumptions": [],
        "steps": [
            {
                "id": f"step_{i}",
                "title": f"Step {i}",
                "instruction": f"Do step {i}",
                "successCriteria": f"Step {i} done",
                "guidanceMode": "point_and_explain",
                "requiresScreenshotCheck": True,
                "canUserMarkDone": True,
                "fallbackHints": [],
                "status": "pending",
            }
            for i in range(steps_count)
        ],
        "pointer": {"x": 500, "y": 300, "label": "Button", "shouldPoint": True},
    }


def _make_evaluation(status="done", confidence=0.9):
    return {
        "status": status,
        "confidence": confidence,
        "rationale": "Looks good",
        "suggestedAction": "advance" if status == "done" else "repeat_guidance",
        "assistantResponse": "Good job!",
    }


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def orchestrator(fresh_session):
    """Return TaskOrchestrator with a fresh session."""
    orchestrator = TaskOrchestrator.__new__(TaskOrchestrator)
    orchestrator._session = fresh_session
    orchestrator._provider = None
    return orchestrator


# ============================================================================
# process_query
# ============================================================================


class TestProcessQuery:
    def test_full_flow(self, orchestrator):
        plan = _make_plan()
        with patch("server.services.agent.orchestrator.plan_and_locate", return_value=plan):
            result = orchestrator.process_query(
                query="Open Chrome",
                image_base64="FAKE_B64",
            )
        assert result["success"] is True
        assert result["plan"]["goal"] == "Test task"
        assert result["plan"]["steps"] is not None
        assert result["pointer"] is not None

    def test_session_status_is_waiting(self, orchestrator):
        plan = _make_plan()
        with patch("server.services.agent.orchestrator.plan_and_locate", return_value=plan):
            orchestrator.process_query(query="Open Chrome")
        snap = orchestrator._session.get_snapshot()
        assert snap["status"] == "waiting_user"

    def test_no_screenshot(self, orchestrator):
        plan = _make_plan()
        with patch("server.services.agent.orchestrator.plan_and_locate", return_value=plan):
            result = orchestrator.process_query(query="Open Chrome", image_base64=None)
        assert result["success"] is True


# ============================================================================
# evaluate_current_step — uses evaluate_step to check completion
# ============================================================================


class TestEvaluateCurrentStep:
    def test_done_advances(self, orchestrator):
        plan = _make_plan()
        plan["current_step_index"] = 0
        plan["steps"][0]["status"] = "active"
        orchestrator._session.set_active_plan(plan)

        eval_result = _make_evaluation(status="done")
        with patch("server.services.agent.orchestrator.evaluate_step", return_value=eval_result):
            with patch("server.services.agent.orchestrator.locate_step_target") as mock_locate:
                mock_locate.return_value = {
                    "x": 300, "y": 200, "label": "Next", "shouldPoint": True,
                }
                result = orchestrator.evaluate_current_step(image_base64="FAKE")
        assert result["action"] == "advance"

    def test_not_done_does_not_advance(self, orchestrator):
        plan = _make_plan()
        plan["current_step_index"] = 0
        plan["steps"][0]["status"] = "active"
        orchestrator._session.set_active_plan(plan)

        eval_result = _make_evaluation(status="not_done")
        with patch("server.services.agent.orchestrator.evaluate_step", return_value=eval_result):
            result = orchestrator.evaluate_current_step(image_base64="FAKE")
        assert result["action"] != "advance"
