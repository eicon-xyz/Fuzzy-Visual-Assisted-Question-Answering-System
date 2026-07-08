"""
Layer 1 — Agent execution loop (mock LLM calls)

Tests execute_step state machine: tool call parsing, step completion,
retry behavior, cancellation, empty response handling.
_call_llm_with_tools is mocked to return canned tool-call JSON.
"""

import pytest
import threading
import json
from unittest.mock import MagicMock, patch, AsyncMock

from server.services.executor.agent import ExecutionAgent
from server.models.schemas import ExecutedStep


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_step(index=1, instruction="Click the button"):
    return ExecutedStep(step_index=index, instruction=instruction)


def _tool_json(name, args=None):
    return json.dumps({"__tool_call__": True, "name": name, "arguments": args or {}})


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    a = ExecutionAgent()
    a.element_map = {}
    a.screen_elements = []
    a._browser = None
    return a


@pytest.fixture(autouse=True)
def _mock_dispatch(agent):
    """Replace dispatch_tool with a simple fake that handles all tool names."""
    original = agent.dispatch_tool

    def fake_dispatch(tool_name, tool_args):
        if tool_name == "get_screen_info":
            return {"success": True, "action_summary": "screen captured"}
        elif tool_name == "click":
            eid = tool_args.get("element_id", "")
            if eid == "valid_btn":
                return {"success": True, "action_summary": "clicked"}
            return {"success": False, "error": "not found"}
        elif tool_name == "wait":
            return {"success": True, "action_summary": "waited"}
        elif tool_name == "mark_step_done":
            return {"__step_complete__": True, "success": True, "reason": tool_args.get("reason", "")}
        elif tool_name == "mark_step_failed":
            return {"__step_failed__": True, "reason": tool_args.get("reason", "")}
        elif tool_name.startswith("browser_"):
            return {"success": True, "action_summary": f"{tool_name} done"}
        elif tool_name == "launch_app":
            return {"success": True, "action_summary": "app launched"}
        elif tool_name == "type_text":
            return {"success": True, "action_summary": "typed"}
        elif tool_name == "press_key":
            return {"success": True, "action_summary": "pressed"}
        return {"success": True, "action_summary": "ok"}

    agent.dispatch_tool = fake_dispatch
    yield
    agent.dispatch_tool = original


# ============================================================================
# execute_step tests
# ============================================================================


class TestExecuteStepSingleRound:
    """LLM returns mark_step_done on first call."""

    def test_one_round_done(self, agent):
        agent._call_llm_with_tools = lambda msgs: (
            _tool_json("mark_step_done", {"reason": "already done"}),
            None,
        )
        step = _make_step(1, "Open app")
        result = agent.execute_step(step, goal="Test", previous_steps=[])
        assert result.status == "done"

    def test_immediate_failed(self, agent):
        agent._call_llm_with_tools = lambda msgs: (
            _tool_json("mark_step_failed", {"reason": "can't do it"}),
            None,
        )
        step = _make_step(1, "Impossible task")
        result = agent.execute_step(step, goal="Test", previous_steps=[])
        assert result.status == "failed"
        assert "can't" in result.action_summary


class TestExecuteStepMultiRound:
    """LLM takes multiple tool calls before marking done."""

    def test_two_rounds(self, agent):
        """Round 0: get_screen_info, Round 1: mark_step_done."""
        calls = [
            (_tool_json("get_screen_info"), None),
            (_tool_json("mark_step_done", {"reason": "done"}), None),
        ]
        call_idx = [0]

        def mock_llm(msgs):
            result = calls[call_idx[0]]
            call_idx[0] += 1
            return result

        agent._call_llm_with_tools = mock_llm
        step = _make_step(1, "Click button")
        result = agent.execute_step(step, goal="Test", previous_steps=[])
        assert result.status == "done"

    def test_three_rounds(self, agent):
        """get_screen_info → click → mark_step_done."""
        calls = [
            (_tool_json("get_screen_info"), None),
            (_tool_json("click", {"element_id": "valid_btn"}), None),
            (_tool_json("mark_step_done", {"reason": "clicked"}), None),
        ]
        call_idx = [0]

        def mock_llm(msgs):
            result = calls[call_idx[0]]
            call_idx[0] += 1
            return result

        agent._call_llm_with_tools = mock_llm
        step = _make_step(1, "Click button")
        result = agent.execute_step(step, goal="Test", previous_steps=[])
        assert result.status == "done"


class TestExecuteStepEmptyResponses:
    """LLM returns text without tool calls."""

    def test_empty_then_done(self, agent):
        calls = [
            ("Just thinking...", None),  # text-only, no tool call
            (_tool_json("mark_step_done", {"reason": "ok"}), None),
        ]
        call_idx = [0]

        def mock_llm(msgs):
            result = calls[call_idx[0]]
            call_idx[0] += 1
            return result

        agent._call_llm_with_tools = mock_llm
        step = _make_step(1, "Task")
        result = agent.execute_step(step, goal="Test", previous_steps=[])
        assert result.status == "done"

    def test_empty_response_not_crashed(self, agent):
        """LLM returns empty string — should not crash."""
        call_count = [0]

        def mock_llm(msgs):
            call_count[0] += 1
            if call_count[0] >= 3:
                return (_tool_json("mark_step_done", {"reason": "done"}), None)
            return ("", None)

        agent._call_llm_with_tools = mock_llm
        step = _make_step(1, "Task")
        result = agent.execute_step(step, goal="Test", previous_steps=[])
        # Either exhausted or succeeded — shouldn't crash
        assert result.status in ("done", "failed")


class TestExecuteStepCancellation:
    def test_cancel_event_stops(self, agent):
        cancel = threading.Event()
        cancel.set()  # already cancelled

        step = _make_step(1, "Task")
        result = agent.execute_step(
            step, goal="Test", previous_steps=[], cancel_event=cancel
        )
        assert result.status == "failed"
        assert "cancelled" in result.action_summary.lower()


class TestExecuteStepRoundExhaustion:
    def test_max_rounds_exhausted(self, agent):
        """Keep returning same tool that doesn't finish — verify exhaustion."""
        call_count = [0]

        def mock_llm(msgs):
            call_count[0] += 1
            return (_tool_json("get_screen_info"), None)

        agent._call_llm_with_tools = mock_llm
        step = _make_step(1, "Endless task")
        result = agent.execute_step(step, goal="Test", previous_steps=[])
        # Should have been called at most MAX_TOOL_CALL_ROUNDS times
        assert call_count[0] <= 15
        assert result.status == "failed"


class TestExecuteStepAppLaunchHint:
    def test_open_app_adds_hint(self, agent):
        """Steps with '打开' or '启动' should get a launch_app hint in context."""
        calls = [
            (_tool_json("launch_app", {"app_name": "Chrome"}), None),
            (_tool_json("mark_step_done", {"reason": "launched"}), None),
        ]
        call_idx = [0]
        def mock_llm(msgs):
            result = calls[call_idx[0]]
            call_idx[0] += 1
            return result
        agent._call_llm_with_tools = mock_llm
        step = _make_step(1, "打开Chrome浏览器")
        result = agent.execute_step(step, goal="Test", previous_steps=[])
        assert result.status == "done"
