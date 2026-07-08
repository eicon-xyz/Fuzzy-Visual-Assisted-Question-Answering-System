import pytest
from unittest.mock import patch, MagicMock
from server.models.schemas import UIElement, ExecutedStep
from server.services.executor.agent import (
    ExecutionAgent, EXECUTION_SYSTEM_PROMPT,
    _build_tool_definitions, _build_context_for_llm,
)


def make_element(eid, content, bbox, left_ids=None, right_ids=None, top_ids=None, bottom_ids=None):
    x1, y1, x2, y2 = bbox
    return UIElement(
        element_id=str(eid), bbox=bbox, element_type="text",
        text=content, confidence=0.9,
        center=[(x1+x2)//2, (y1+y2)//2],
        left_elem_ids=left_ids or [],
        right_elem_ids=right_ids or [],
        top_elem_ids=top_ids or [],
        bottom_elem_ids=bottom_ids or [],
    )


class TestElementMap:
    def test_element_map_lookup(self):
        agent = ExecutionAgent()
        el = make_element("3", "search", [100, 200, 300, 400])
        agent.element_map = {"3": el}
        assert agent.element_map["3"].element_id == "3"
        assert agent.element_map["3"].text == "search"

    def test_clear_element_map(self):
        agent = ExecutionAgent()
        agent.element_map = {"3": make_element("3", "x", [0, 0, 10, 10])}
        agent.clear_element_map()
        assert agent.element_map == {}

    def test_stale_element_id_returns_error(self):
        agent = ExecutionAgent()
        agent.element_map = {}
        result = agent._do_click("99")
        assert result["success"] == False
        assert "not found" in result["error"]
        assert "get_screen_info" in result["error"]


class TestContextBuilder:
    def test_context_includes_goal_and_step(self):
        ctx = _build_context_for_llm(
            goal="test goal",
            current_step={"index": 2, "instruction": "do thing"},
            previous_steps=[
                {"index": 1, "instruction": "open app", "status": "done",
                 "action_summary": "launched 'App'"},
            ]
        )
        assert "test goal" in ctx
        assert "do thing" in ctx
        assert "launched 'App'" in ctx


class TestToolDefinitions:
    def test_all_tools_have_names_and_params(self):
        tools = _build_tool_definitions()
        tool_names = {t["function"]["name"] for t in tools}
        assert "get_screen_info" in tool_names
        assert "click" in tool_names
        assert "double_click" in tool_names
        assert "type_text" in tool_names
        assert "press_key" in tool_names
        assert "launch_app" in tool_names
        assert "mark_step_done" in tool_names
        assert "mark_step_failed" in tool_names
        # Verify click takes element_id (not coordinates)
        click_tool = [t for t in tools if t["function"]["name"] == "click"][0]
        params = click_tool["function"]["parameters"]["properties"]
        assert "element_id" in params
        assert "bbox_center" not in params
        assert "x" not in params


class TestDispatchTool:
    def test_dispatch_mark_step_done(self):
        agent = ExecutionAgent()
        result = agent.dispatch_tool("mark_step_done", {"reason": "all good"})
        assert result["__step_complete__"] is True
        assert result["success"] is True

    def test_dispatch_mark_step_failed(self):
        agent = ExecutionAgent()
        result = agent.dispatch_tool("mark_step_failed", {"reason": "something broke"})
        assert result["__step_failed__"] is True
        assert result["reason"] == "something broke"

    def test_dispatch_unknown_tool(self):
        agent = ExecutionAgent()
        result = agent.dispatch_tool("nonexistent", {})
        assert result["success"] is False
        assert "Unknown tool" in result["error"]


class TestParseToolCall:
    def test_parse_tool_call_json(self):
        agent = ExecutionAgent()
        raw = '{"__tool_call__": true, "name": "click", "arguments": {"element_id": "5"}}'
        name, args = agent._parse_tool_call(raw)
        assert name == "click"
        assert args == {"element_id": "5"}

    def test_parse_tool_call_non_json(self):
        agent = ExecutionAgent()
        name, args = agent._parse_tool_call("just some text")
        assert name is None
        assert args == {}


class TestExecuteStepCancel:
    def test_execute_step_cancelled(self):
        step = ExecutedStep(step_index=1, instruction="do something")
        cancel = MagicMock()
        cancel.is_set.return_value = True
        agent = ExecutionAgent()
        result = agent.execute_step(step, "goal", [], cancel)
        assert result.status == "failed"
        assert "cancelled" in result.action_summary
