"""
Layer 1 — LLM Chains prompt construction (mock call_llm/call_llm_json)

Tests that each chain function builds the correct prompt,
parses the response correctly, and handles edge cases.
No real LLM calls — call_llm and call_llm_json are mocked.
"""

import pytest
from unittest.mock import patch

from server.services.agent import prompts as P
from server.services.agent.chains import (
    plan_and_locate,
    plan_goal,
    locate_step_target,
    evaluate_step,
    replan_goal,
    fast_mode_chat,
    _build_step_dicts,
    _summarize_screenshots,
)
from server.services.llm.providers import DEFAULT_SYSTEM_PROMPT


# ── Fixture ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_memory_retriever():
    """Prevent memory retrieval from blocking chain tests."""
    with patch("server.services.agent.chains.get_retriever") as mock_get:
        mock_retriever = mock_get.return_value
        mock_retriever.retrieve.return_value = ""  # no memories
        yield


# ============================================================================
# plan_and_locate
# ============================================================================


class TestPlanAndLocate:
    def test_builds_correct_prompt(self):
        raw_llm = '{"goal":"Open Chrome","assistantResponse":"Click [POINT:500,300:Icon]","steps":[{"id":"s1","title":"Click","instruction":"Click icon"}],"pointer":{"x":500,"y":300,"label":"Icon","shouldPoint":true}}'

        with patch("server.services.agent.chains.call_llm", return_value=raw_llm):
            result = plan_and_locate(goal="Open Chrome", image_base64="FAKE")

        assert result["goal"] == "Open Chrome"
        assert len(result["steps"]) == 1
        assert result["pointer"]["x"] == 500

    def test_no_image(self):
        raw_llm = '{"goal":"Test","steps":[],"pointer":{}}'
        with patch("server.services.agent.chains.call_llm", return_value=raw_llm):
            result = plan_and_locate(goal="Test", image_base64=None)

        assert result["goal"] == "Test"
        assert result["steps"] == []

    def test_fallback_point_from_response(self):
        """Pointer harvested from assistantResponse POINT tag."""
        raw_llm = '{"goal":"Click","assistantResponse":"Click here [POINT:300,400:Button]","steps":[],"pointer":{}}'
        with patch("server.services.agent.chains.call_llm", return_value=raw_llm):
            result = plan_and_locate(goal="Click")

        assert result["pointer"]["x"] == 300
        assert result["pointer"]["y"] == 400

    def test_memory_failure_does_not_block(self):
        """If memory retrieval crashes, plan_and_locate still works."""
        raw_llm = '{"goal":"Test","steps":[],"pointer":{}}'
        with patch("server.services.agent.chains.call_llm", return_value=raw_llm):
            with patch("server.services.agent.chains.get_retriever") as mock_get:
                mock_get.side_effect = RuntimeError("DB down")
                result = plan_and_locate(goal="Test")
        assert result["goal"] == "Test"


# ============================================================================
# plan_goal
# ============================================================================


class TestPlanGoal:
    def test_basic(self):
        with patch("server.services.agent.chains.call_llm_json") as mock_json:
            mock_json.return_value = {
                "goal": "Install app",
                "assistantResponse": "OK",
                "assumptions": [],
                "steps": [{"id": "s1", "title": "Download", "instruction": "Download it"}],
            }
            result = plan_goal(goal="Install app")
        assert result["goal"] == "Install app"
        assert len(result["steps"]) == 1

    def test_steps_are_normalized(self):
        with patch("server.services.agent.chains.call_llm_json") as mock_json:
            mock_json.return_value = {"goal": "X", "steps": [{"title": "S1", "instruction": "Do"}]}
            result = plan_goal(goal="X")
        step = result["steps"][0]
        assert "status" in step
        assert step["status"] == "pending"


# ============================================================================
# locate_step_target
# ============================================================================


class TestLocateStepTarget:
    def test_finds_coordinate(self):
        with patch("server.services.agent.chains.call_llm_json") as mock_json:
            mock_json.return_value = {
                "coordinate": {"x": 500, "y": 300},
                "label": "Button",
                "shouldPoint": True,
            }
            result = locate_step_target(
                goal="Find button",
                step={"title": "Click", "instruction": "Click the button"},
            )
        assert result["x"] == 500
        assert result["y"] == 300

    def test_strict_retry_when_no_coord(self):
        """force_point=True + first call no coord → second call with strict prompt."""
        responses = [
            {"coordinate": None, "label": "?", "shouldPoint": False},
            {"coordinate": {"x": 100, "y": 200}, "label": "Found", "shouldPoint": True},
        ]
        call_idx = [0]

        def side_effect(*args, **kwargs):
            result = responses[call_idx[0]]
            call_idx[0] += 1
            return result

        with patch("server.services.agent.chains.call_llm_json", side_effect=side_effect):
            result = locate_step_target(
                goal="Find",
                step={"title": "Click", "instruction": "Click it"},
                image_base64="FAKE",
                force_point=True,
            )
        assert result["x"] == 100
        assert result["shouldPoint"] is True
        assert call_idx[0] == 2  # called twice

    def test_no_strict_retry_without_image(self):
        """force_point without image_base64 skips strict retry."""
        with patch("server.services.agent.chains.call_llm_json") as mock_json:
            mock_json.return_value = {"coordinate": None, "label": "?", "shouldPoint": False}
            result = locate_step_target(
                goal="Find",
                step={"title": "X", "instruction": "Y"},
                force_point=True,
                image_base64=None,
            )
        assert mock_json.call_count == 1


# ============================================================================
# evaluate_step
# ============================================================================


class TestEvaluateStep:
    def test_returns_evaluation(self):
        with patch("server.services.agent.chains.call_llm_json") as mock_json:
            mock_json.return_value = {
                "status": "done",
                "confidence": 0.95,
                "rationale": "Looks done",
                "suggestedAction": "advance",
                "assistantResponse": "Good!",
            }
            result = evaluate_step(
                goal="Test",
                step={"title": "X", "instruction": "Y", "successCriteria": "Z"},
            )
        assert result["status"] == "done"
        assert result["confidence"] == 0.95

    def test_disabled_returns_done(self):
        """When EVALUATOR_ENABLED is False, skip LLM call."""
        with patch("server.services.agent.chains.EVALUATOR_ENABLED", False):
            result = evaluate_step(
                goal="Test",
                step={"title": "X", "instruction": "Y"},
            )
        assert result["status"] == "done"
        assert result["confidence"] == 1.0

    def test_llm_error_defaults_to_advance(self):
        with patch("server.services.agent.chains.call_llm_json", side_effect=RuntimeError("API down")):
            result = evaluate_step(
                goal="Test",
                step={"title": "X", "instruction": "Y"},
            )
        assert result["status"] == "done"
        assert result["suggestedAction"] == "advance"


# ============================================================================
# replan_goal
# ============================================================================


class TestReplanGoal:
    def test_replans(self):
        with patch("server.services.agent.chains.call_llm_json") as mock_json:
            mock_json.return_value = {
                "goal": "Revised goal",
                "assistantResponse": "Adjusted",
                "assumptions": [],
                "steps": [{"title": "New step", "instruction": "Do it differently"}],
            }
            result = replan_goal(
                goal="Old goal",
                failed_step_title="Broken step",
                rationale="Element not found",
            )
        assert result["goal"] == "Revised goal"
        assert len(result["steps"]) == 1


# ============================================================================
# fast_mode_chat
# ============================================================================


class TestFastModeChat:
    def test_basic_chat(self):
        with patch("server.services.agent.chains.call_llm", return_value="Hello!"):
            response = fast_mode_chat(text="Hi")
        assert response == "Hello!"

    def test_with_screenshot(self):
        with patch("server.services.agent.chains.call_llm", return_value="I see it."):
            response = fast_mode_chat(text="What's this?", image_base64="FAKE")
        assert len(response) > 0
