"""
Integration tests: Planning → Execution Agent pipeline.

Mock LLM responses to exercise the full agent loop without touching
a real screen or making real LLM/OmniParser HTTP calls.
"""
import json
import pytest
import threading
from unittest.mock import patch, MagicMock

from server.services.planning.planner import plan_steps, PlanningResult
from server.services.executor.agent import ExecutionAgent
from server.models.schemas import ExecutedStep, UIElement


class TestPlanningToExecution:
    """Integration: Planning output feeds into Execution Agent input."""

    @patch("server.services.planning.planner.call_llm")
    def test_plan_output_compatible_with_execution(self, mock_llm):
        mock_llm.return_value = json.dumps({
            "goal": "test goal",
            "steps": [
                {"step_index": 1, "instruction": "step one"},
                {"step_index": 2, "instruction": "step two"},
            ]
        })
        result = plan_steps("do something")
        assert len(result.steps) == 2
        # Convert to ExecutedStep
        for ps in result.steps:
            es = ExecutedStep(step_index=ps.step_index, instruction=ps.instruction)
            assert es.instruction == ps.instruction
            assert es.status == "pending"


class TestMockExecutionLoop:
    """Full agent loop with mocked LLM returning preset tool calls."""

    def make_agent_with_elements(self):
        agent = ExecutionAgent()
        el = UIElement(
            element_id="1", bbox=[100, 200, 300, 400], element_type="text",
            text="搜索框", confidence=0.9, center=[200, 300],
        )
        agent.element_map = {"1": el}
        return agent

    @patch.object(ExecutionAgent, '_call_llm_with_tools')
    def test_step_click_flow(self, mock_llm):
        """Simulate: get_screen_info -> click -> mark_step_done."""
        call_count = [0]

        def mock_call(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "get_screen_info",
                    "arguments": {},
                }), None  # (raw, assistant_msg) tuple
            elif call_count[0] == 2:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "click",
                    "arguments": {"element_id": "1"},
                }), None
            else:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "mark_step_done",
                    "arguments": {"reason": "click successful"},
                }), None

        mock_llm.side_effect = mock_call

        # Mock _do_get_screen_info to avoid real screenshot + OmniParser
        # and pyautogui to avoid real mouse movement
        with patch.object(ExecutionAgent, '_do_get_screen_info') as mock_scan, \
             patch('pyautogui.moveTo'), \
             patch('pyautogui.click'):

            mock_scan.return_value = {
                "success": True, "elements": [], "element_count": 0
            }

            agent = self.make_agent_with_elements()
            step = ExecutedStep(step_index=1, instruction="点击搜索框")
            result = agent.execute_step(step, "test goal", [])

        assert result.status == "done"

    @patch.object(ExecutionAgent, '_call_llm_with_tools')
    def test_step_failure_signal(self, mock_llm):
        """Simulate: get_screen_info -> mark_step_failed (element not found)."""
        call_count = [0]

        def mock_call(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "get_screen_info",
                    "arguments": {},
                }), None
            else:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "mark_step_failed",
                    "arguments": {"reason": "element not found on screen"},
                }), None

        mock_llm.side_effect = mock_call

        with patch.object(ExecutionAgent, '_do_get_screen_info') as mock_scan:
            mock_scan.return_value = {
                "success": True, "elements": [], "element_count": 0
            }

            agent = self.make_agent_with_elements()
            step = ExecutedStep(step_index=1, instruction="点击不存在的按钮")
            result = agent.execute_step(step, "test goal", [])

        assert result.status == "failed"

    @patch.object(ExecutionAgent, '_call_llm_with_tools')
    def test_precondition_already_satisfied(self, mock_llm):
        """Simulate: LLM immediately calls mark_step_done with precondition text."""
        mock_llm.return_value = (json.dumps({
            "__tool_call__": True,
            "name": "mark_step_done",
            "arguments": {"reason": "precondition already satisfied"},
        }), None)

        agent = ExecutionAgent()
        step = ExecutedStep(step_index=2, instruction="打开浏览器应用")
        result = agent.execute_step(
            step, "open browser and search",
            [{"index": 1, "instruction": "打开浏览器应用", "status": "done",
              "action_summary": "launched app 'Chrome' via Win+Search"}],
        )
        assert result.status == "done"

    def test_cancel_mid_step(self):
        """Cancel event set before execute_step should abort."""
        agent = ExecutionAgent()
        step = ExecutedStep(step_index=1, instruction="test")
        cancel_event = threading.Event()
        cancel_event.set()  # already cancelled
        result = agent.execute_step(step, "goal", [], cancel_event=cancel_event)
        assert result.status == "failed"
        assert "cancelled" in (result.action_summary or "").lower()

    def test_stale_element_id_after_rescan(self):
        """After second get_screen_info, old element_ids are invalid."""
        agent = ExecutionAgent()
        el = UIElement(
            element_id="1", bbox=[0, 0, 10, 10], element_type="text",
            text="test", confidence=0.9, center=[5, 5],
        )
        agent.element_map = {"1": el}

        # Simulate get_screen_info with new elements — the real
        # _do_get_screen_info rebuilds element_map from scratch,
        # so old entries vanish.  We replicate that via side_effect.
        with patch.object(agent, '_do_get_screen_info') as mock_scan:
            def scan_and_clear():
                agent.element_map = {}
                return {"success": True, "elements": [], "element_count": 0}
            mock_scan.side_effect = scan_and_clear
            agent._do_get_screen_info()

        # Old element "1" is gone
        result = agent._do_click("1")
        assert result["success"] is False
        assert "not found" in result["error"]
