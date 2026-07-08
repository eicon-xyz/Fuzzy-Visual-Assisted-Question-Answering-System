"""
Layer 0 — Pure Function Unit Tests

Every function tested here has ZERO external dependencies.
No mocks, no real LLM, no browser, no display needed.
Runs in ~1 second, no network, no filesystem access beyond source imports.

Coverage:
  0.1  coords.py       — normalize, clamp, validate, postprocess
  0.2  providers.py    — parse_point_tags
  0.3  providers.py    — extract_json_object, parse_structured_json
  0.4  providers.py    — _strip_data_uri_prefix, _detect_mime
  0.5  safety.py       — check_step red/yellow/green
  0.6  agent.py        — _build_tool_definitions
  0.7  agent.py        — _parse_tool_call
  0.8  agent/chains.py — _build_context_for_llm, _summarize_screenshots, _build_step_dicts
  0.9  prompts.py      — all 8 template strings
  0.10 session/manager — SessionManager full state machine
  0.11 schemas.py      — Pydantic model validation
"""

import pytest
from pydantic import ValidationError

from server.models.schemas import ExecutedStep, UIElement

# ============================================================================
# 0.1 Coordinate system
# ============================================================================

from server.services.validation.coords import (
    clamp_to_bounds,
    normalize_coordinate,
    validate_coordinate,
)


class TestNormalizeCoordinate:
    def test_center_maps_to_center(self):
        """(500, 500) on 1920x1080 → (960, 540)"""
        x, y = normalize_coordinate(500, 500, 1920, 1080)
        assert x == 960
        assert y == 540

    def test_top_left_is_zero(self):
        x, y = normalize_coordinate(0, 0, 1920, 1080)
        assert x == 0
        assert y == 0

    def test_bottom_right_is_max(self):
        x, y = normalize_coordinate(1000, 1000, 1920, 1080)
        assert x == 1920
        assert y == 1080

    def test_custom_resolution(self):
        x, y = normalize_coordinate(500, 500, 2560, 1440)
        assert x == 1280
        assert y == 720


class TestClampToBounds:
    def test_within_bounds_passes_through(self):
        cx, cy, clamped = clamp_to_bounds(100, 100, 1920, 1080)
        assert cx == 100
        assert cy == 100
        assert clamped is False

    def test_left_edge_clamped(self):
        cx, cy, clamped = clamp_to_bounds(2, 500, 1920, 1080, margin=10)
        assert cx == 10
        assert cy == 500
        assert clamped is True

    def test_right_edge_clamped(self):
        cx, cy, clamped = clamp_to_bounds(1918, 500, 1920, 1080, margin=10)
        assert cx == 1910
        assert clamped is True

    def test_both_edges_clamped(self):
        cx, cy, clamped = clamp_to_bounds(0, 1080, 1920, 1080, margin=10)
        assert cx == 10
        assert cy == 1070
        assert clamped is True


class TestValidateCoordinate:
    def test_valid_passes_through(self):
        x, y, valid = validate_coordinate(500, 300, 1920, 1080)
        assert x == 500
        assert y == 300
        assert valid is True

    def test_out_of_bounds_clamped(self):
        x, y, valid = validate_coordinate(-10, 2000, 1920, 1080)
        assert valid is True
        assert 0 <= x <= 1920
        assert 0 <= y <= 1080


# ============================================================================
# 0.1b  Postprocess (uses module-level _history — carefully reset)
# ============================================================================

from server.services.validation.postprocess import postprocess_pointer, reset_history


class TestPostprocessPointer:
    def teardown_method(self):
        reset_history()

    def test_normal_conversion(self):
        result = postprocess_pointer(500, 300, "Button", 1920, 1080)
        assert result["x"] == 960
        assert result["y"] == 324
        assert result["clamped"] is False
        assert result["jumped"] is False

    def test_out_of_bounds_clamped(self):
        result = postprocess_pointer(-100, 2000, "Bad", 1920, 1080)
        assert result["clamped"] is True

    def test_consecutive_no_jump(self):
        r1 = postprocess_pointer(500, 500, "A", 1920, 1080)
        r2 = postprocess_pointer(510, 510, "B", 1920, 1080)
        assert r1["jumped"] is False
        assert r2["jumped"] is False  # nearby — no jump

    def test_large_jump_triggers_smoothing(self):
        postprocess_pointer(100, 100, "A", 1920, 1080)
        r2 = postprocess_pointer(900, 900, "B", 1920, 1080)
        assert r2["jumped"] is True


# ============================================================================
# 0.2 POINT tag parsing
# ============================================================================

from server.services.llm.providers import parse_point_tags


class TestParsePointTags:
    def test_standard_point_tag(self):
        result = parse_point_tags("Click here [POINT:500,300:Submit Button]")
        assert result["coordinate"] == {"x": 500.0, "y": 300.0}
        assert result["label"] == "Submit Button"
        assert result["spokenText"] == "Click here"

    def test_multiscreen_tag(self):
        result = parse_point_tags("Open [POINT:200,100:Menu:screen2]")
        assert result["coordinate"] == {"x": 200.0, "y": 100.0}
        assert result["screenNumber"] == 2

    def test_point_none(self):
        result = parse_point_tags("No pointing [POINT:none] needed")
        assert result["coordinate"] is None
        assert result["label"] is None

    def test_chinese_label(self):
        result = parse_point_tags("点击 [POINT:800,200:搜索按钮] 这里")
        assert result["coordinate"] == {"x": 800.0, "y": 200.0}
        assert result["label"] == "搜索按钮"
        assert "点击" in result["spokenText"]

    def test_float_coordinates(self):
        result = parse_point_tags("At [POINT:123.45,678.90:element]")
        assert result["coordinate"] == {"x": 123.45, "y": 678.90}

    def test_fallback_paren_format(self):
        result = parse_point_tags("Look at (150, 250)")
        assert result["coordinate"] == {"x": 150.0, "y": 250.0}
        assert "Look at" in result["spokenText"]

    def test_plain_text_no_coords(self):
        result = parse_point_tags("Just some regular text")
        assert result["coordinate"] is None
        assert result["label"] is None
        assert result["spokenText"] == "Just some regular text"

    def test_multiple_points_returns_first(self):
        result = parse_point_tags(
            "[POINT:100,200:First] and [POINT:300,400:Second]"
        )
        assert result["coordinate"] == {"x": 100.0, "y": 200.0}
        assert result["label"] == "First"


# ============================================================================
# 0.3 JSON extraction
# ============================================================================

from server.services.llm.providers import extract_json_object, parse_structured_json


class TestExtractJsonObject:
    def test_pure_json(self):
        data = extract_json_object('{"goal": "test", "steps": []}')
        assert data["goal"] == "test"
        assert data["steps"] == []

    def test_code_fence_json(self):
        raw = '```json\n{"goal": "test", "steps": []}\n```'
        data = extract_json_object(raw)
        assert data["goal"] == "test"

    def test_code_fence_no_lang(self):
        raw = '```\n{"goal": "test", "steps": []}\n```'
        data = extract_json_object(raw)
        assert data["goal"] == "test"

    def test_qwen_plan_to_steps(self):
        raw = '{"plan": ["Step 1", "Step 2"]}'
        data = extract_json_object(raw)
        assert len(data["steps"]) == 2
        assert data["steps"][0]["instruction"] == "Step 1"

    def test_string_steps_get_dicts(self):
        raw = '{"goal": "test", "steps": ["A", "B"]}'
        data = extract_json_object(raw)
        assert len(data["steps"]) == 2
        assert isinstance(data["steps"][0], dict)
        assert data["steps"][0]["instruction"] == "A"

    def test_trailing_comma_repaired(self):
        raw = '{"goal": "test", "steps": [{"title": "X", "instruction": "Y"},]}'
        data = extract_json_object(raw)
        assert data["goal"] == "test"

    def test_line_comments_stripped(self):
        raw = '{"goal": "test", // comment\n"steps": []}'
        data = extract_json_object(raw)
        assert data["goal"] == "test"

    def test_bom_stripped(self):
        raw = '﻿{"goal": "test", "steps": []}'
        data = extract_json_object(raw)
        assert data["goal"] == "test"

    def test_reasoning_before_json(self):
        raw = "Sure! Here's the plan:\n{\"goal\": \"test\", \"steps\": []}"
        data = extract_json_object(raw)
        assert data["goal"] == "test"

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            extract_json_object("No JSON here at all")

    def test_default_keys_added(self):
        raw = '{"steps": []}'
        data = extract_json_object(raw)
        assert data["goal"] == "Complete the task"
        assert data["assistantResponse"] is not None
        assert data["assumptions"] == []


class TestParseStructuredJson:
    def test_non_locator_returns_extracted(self):
        result = parse_structured_json('{"goal": "test", "steps": []}')
        assert result["goal"] == "test"

    def test_locator_mode_with_json(self):
        result = parse_structured_json(
            '{"coordinate": {"x": 500, "y": 300}, "label": "Btn", "shouldPoint": true}',
            is_locator=True,
        )
        assert result["coordinate"] == {"x": 500, "y": 300}
        assert result["label"] == "Btn"

    def test_locator_fallback_to_point_tag(self):
        result = parse_structured_json(
            "Could not parse but [POINT:700,400:Menu] is there",
            is_locator=True,
        )
        assert result["coordinate"] == {"x": 700.0, "y": 400.0}
        assert result["label"] == "Menu"

    def test_locator_empty_input(self):
        result = parse_structured_json("", is_locator=True)
        assert result["shouldPoint"] is True
        assert "explanation" in result


# ============================================================================
# 0.4 Image helpers
# ============================================================================

from server.services.llm.providers import _detect_mime, _strip_data_uri_prefix


class TestStripDataUriPrefix:
    def test_jpeg_data_uri(self):
        result = _strip_data_uri_prefix("data:image/jpeg;base64,/9j/4AAQ")
        assert result == "/9j/4AAQ"

    def test_png_data_uri(self):
        result = _strip_data_uri_prefix("data:image/png;base64,iVBORw0K")
        assert result == "iVBORw0K"

    def test_pure_base64_passes_through(self):
        result = _strip_data_uri_prefix("iVBORw0KGgo")
        assert result == "iVBORw0KGgo"


class TestDetectMime:
    def test_jpeg_detected(self):
        assert _detect_mime("data:image/jpeg;base64,...") == "image/jpeg"

    def test_default_png(self):
        assert _detect_mime("data:image/png;base64,...") == "image/png"
        assert _detect_mime("data:image/gif;base64,...") == "image/png"


# ============================================================================
# 0.5 Safety checks
# ============================================================================

from server.services.executor.safety import SafetyResult, check_step


class TestSafetyRedBlock:
    def test_steal_password_blocked(self):
        r = check_step("extract password from the browser")
        assert r.allowed is False
        assert r.level == "red"

    def test_format_disk_blocked(self):
        r = check_step("format D:")
        assert r.allowed is False
        assert r.level == "red"

    def test_rm_rf_blocked(self):
        r = check_step("rm -rf /")
        assert r.allowed is False
        assert r.level == "red"

    def test_hack_attempt_blocked(self):
        r = check_step("hack into the server")
        assert r.allowed is False
        assert r.level == "red"

    def test_surveillance_blocked(self):
        r = check_step("monitor other keyboard")
        assert r.allowed is False
        assert r.level == "red"

    def test_brute_force_blocked(self):
        r = check_step("brute force the password")
        assert r.allowed is False
        assert r.level == "red"


class TestSafetyYellowWarn:
    def test_install_software_warned(self):
        r = check_step("install software from the web")
        assert r.allowed is True
        assert r.level == "yellow"

    def test_download_file_warned(self):
        r = check_step("download file from the internet")
        assert r.allowed is True
        assert r.level == "yellow"

    def test_modify_system_warned(self):
        r = check_step("modify system settings")
        assert r.allowed is True
        assert r.level == "yellow"

    def test_delete_file_warned(self):
        r = check_step("delete file permanently")
        assert r.allowed is True
        assert r.level == "yellow"


class TestSafetyGreenOverride:
    def test_open_browser_green(self):
        r = check_step("open Chrome browser")
        assert r.allowed is True
        assert r.level == "green"

    def test_type_search_green(self):
        r = check_step("type search query into the box")
        assert r.allowed is True
        assert r.level == "green"

    def test_click_button_green(self):
        r = check_step("click the submit button")
        assert r.allowed is True
        assert r.level == "green"

    def test_create_folder_green(self):
        r = check_step("create a new folder on desktop")
        assert r.allowed is True
        assert r.level == "green"


class TestSafetyEdgeCases:
    def test_empty_string(self):
        r = check_step("")
        assert r.allowed is True
        assert r.level == "green"

    def test_none_input(self):
        r = check_step(None)
        assert r.allowed is True
        assert r.level == "green"

    def test_whitespace_only(self):
        r = check_step("   ")
        assert r.allowed is True
        assert r.level == "green"

    def test_install_to_d_drive_green(self):
        """'install X to D drive' should not be flagged as install software"""
        r = check_step("install the game to D drive")
        assert r.level == "green"


class TestSafetyResultDataclass:
    def test_construct(self):
        sr = SafetyResult(allowed=False, level="red", reason="blocked")
        assert sr.allowed is False
        assert sr.level == "red"


# ============================================================================
# 0.6 Tool definitions
# ============================================================================

from server.services.executor.agent import _build_tool_definitions


class TestBuildToolDefinitions:
    def test_total_count_is_18(self):
        tools = _build_tool_definitions()
        assert len(tools) == 18

    def test_all_have_type_function(self):
        for t in _build_tool_definitions():
            assert t["type"] == "function"
            assert "name" in t["function"]

    def test_all_names_unique(self):
        names = [t["function"]["name"] for t in _build_tool_definitions()]
        assert len(names) == len(set(names))

    def test_required_params_in_properties(self):
        for t in _build_tool_definitions():
            required = t["function"]["parameters"].get("required", [])
            properties = t["function"]["parameters"].get("properties", {})
            for r in required:
                assert r in properties, f"{t['function']['name']}: required '{r}' not in properties"

    def test_browser_tools_count_is_8(self):
        browser = [
            t["function"]["name"]
            for t in _build_tool_definitions()
            if t["function"]["name"].startswith("browser_")
        ]
        assert len(browser) == 8
        assert "browser_navigate" in browser
        assert "browser_snapshot" in browser
        assert "browser_click" in browser
        assert "browser_type" in browser
        assert "browser_scroll" in browser
        assert "browser_close" in browser
        assert "browser_screenshot" in browser
        assert "browser_press_key" in browser

    def test_desktop_tools_count_is_10(self):
        desktop = [
            t["function"]["name"]
            for t in _build_tool_definitions()
            if not t["function"]["name"].startswith("browser_")
        ]
        assert len(desktop) == 10
        assert "launch_app" in desktop
        assert "get_screen_info" in desktop
        assert "click" in desktop
        assert "mark_step_done" in desktop
        assert "mark_step_failed" in desktop


# ============================================================================
# 0.7 Tool call parsing
# ============================================================================

from server.services.executor.agent import ExecutionAgent


def _parse(text):
    """Convenience wrapper for testing."""
    agent = ExecutionAgent()
    return agent._parse_tool_call(text)


class TestParseToolCall:
    def test_standard_tool_call(self):
        name, args = _parse(
            '{"__tool_call__": true, "name": "click", '
            '"arguments": {"element_id": "btn1"}}'
        )
        assert name == "click"
        assert args == {"element_id": "btn1"}

    def test_fallback_name_and_arguments(self):
        name, args = _parse(
            '{"name": "type_text", "arguments": {"element_id": "in", "text": "hi"}}'
        )
        assert name == "type_text"
        assert args == {"element_id": "in", "text": "hi"}

    def test_fallback_tool_and_args(self):
        name, args = _parse(
            '{"tool": "press_key", "args": {"keys": "enter"}}'
        )
        assert name == "press_key"
        assert args == {"keys": "enter"}

    def test_empty_string(self):
        name, args = _parse("")
        assert name is None
        assert args == {}

    def test_plain_text_no_tool(self):
        name, args = _parse("The button has been clicked")
        assert name is None

    def test_json_decode_error(self):
        name, args = _parse("not json at all {{{")
        assert name is None

    def test_mark_step_done(self):
        name, args = _parse(
            '{"__tool_call__": true, "name": "mark_step_done", '
            '"arguments": {"reason": "done"}}'
        )
        assert name == "mark_step_done"


# ============================================================================
# 0.8 Context builders
# ============================================================================

from server.services.executor.agent import _build_context_for_llm
from server.services.agent.chains import _build_step_dicts, _summarize_screenshots


class TestBuildContextForLLM:
    def test_no_history(self):
        ctx = _build_context_for_llm("Install app", {"index": 1, "instruction": "Open"}, [])
        assert "Install app" in ctx
        assert "Step 1" in ctx
        assert "已完成的步骤" not in ctx

    def test_with_previous_steps(self):
        ctx = _build_context_for_llm(
            "Install app",
            {"index": 2, "instruction": "Type"},
            [{"index": 1, "instruction": "Open", "action_summary": "launched"}],
        )
        assert "已完成的步骤" in ctx
        assert "launched" in ctx
        assert "Step 2" in ctx

    def test_multiple_previous_steps(self):
        ctx = _build_context_for_llm(
            "Setup",
            {"index": 3, "instruction": "Configure"},
            [
                {"index": 1, "instruction": "Open", "action_summary": "launched"},
                {"index": 2, "instruction": "Click", "action_summary": "clicked"},
            ],
        )
        assert "Step 1" in ctx
        assert "Step 2" in ctx
        assert "Step 3" in ctx


class TestSummarizeScreenshots:
    def test_none_input(self):
        assert _summarize_screenshots(None) == "No screenshot attached."

    def test_empty_list(self):
        assert _summarize_screenshots([]) == "No screenshot attached."

    def test_single_screenshot(self):
        result = _summarize_screenshots(
            [{"label": "Screen", "width": 1920, "height": 1080}]
        )
        assert "Screen 1" in result
        assert "1920x1080" in result

    def test_multiple_screenshots(self):
        result = _summarize_screenshots(
            [
                {"label": "Main", "width": 1920, "height": 1080},
                {"label": "Secondary", "width": 1280, "height": 720},
            ]
        )
        assert "Screen 1" in result
        assert "Screen 2" in result
        assert "Main" in result
        assert "Secondary" in result


class TestBuildStepDicts:
    def test_string_steps(self):
        steps = _build_step_dicts(["Do A", "Do B"])
        assert len(steps) == 2
        assert steps[0]["instruction"] == "Do A"
        assert steps[0]["id"] == "step_0"
        assert steps[0]["status"] == "pending"

    def test_dict_steps_preserve_fields(self):
        steps = _build_step_dicts([
            {"id": "s1", "title": "Step 1", "instruction": "Do X", "guidanceMode": "just_explain"}
        ])
        assert len(steps) == 1
        assert steps[0]["guidanceMode"] == "just_explain"
        assert steps[0]["id"] == "s1"

    def test_start_index_offset(self):
        steps = _build_step_dicts(["A", "B"], start_index=5)
        assert steps[0]["id"] == "step_5"
        assert steps[1]["id"] == "step_6"

    def test_empty_list(self):
        assert _build_step_dicts([]) == []


# ============================================================================
# 0.9 Prompt templates
# ============================================================================

from server.services.agent import prompts as P


class TestPromptTemplates:
    """Verify every template .format() succeeds without KeyError."""

    def test_plan_locate_combo_system(self):
        assert "HAJIMI" in P.PLAN_LOCATE_COMBO_SYSTEM
        assert "POINT" in P.PLAN_LOCATE_COMBO_SYSTEM

    def test_plan_locate_combo_user_format(self):
        result = P.PLAN_LOCATE_COMBO_USER.format(
            goal="test", recentMessages="none", screenHints="none", user_memory=""
        )
        assert "test" in result

    def test_planner_system(self):
        assert "2-5" in P.PLANNER_SYSTEM_PROMPT

    def test_planner_user_format(self):
        result = P.PLANNER_USER_TEMPLATE.format(
            goal="test", recentMessages="none", screenHints="none", user_memory=""
        )
        assert "test" in result

    def test_locator_system(self):
        assert "0 to 1000" in P.LOCATOR_SYSTEM_PROMPT

    def test_locator_user_format(self):
        result = P.LOCATOR_USER_TEMPLATE.format(
            goal="test", stepTitle="Click", instruction="Click the button"
        )
        assert "Click" in result

    def test_evaluator_system(self):
        assert "done" in P.EVALUATOR_SYSTEM_PROMPT
        assert "not_done" in P.EVALUATOR_SYSTEM_PROMPT

    def test_evaluator_user_format(self):
        result = P.EVALUATOR_USER_TEMPLATE.format(
            goal="test", stepTitle="X", instruction="Y", successCriteria="Z"
        )
        assert "X" in result

    def test_replanner_system(self):
        assert "adjust" in P.REPLANNER_SYSTEM_PROMPT.lower()

    def test_replanner_user_format(self):
        result = P.REPLANNER_USER_TEMPLATE.format(
            goal="test", failedStepTitle="Bad", rationale="not working"
        )
        assert "Bad" in result
        assert "not working" in result

    def test_strict_locator_system(self):
        assert "STRICT" in P.STRICT_LOCATOR_SYSTEM_PROMPT


# ============================================================================
# 0.10 Session Manager state machine
# ============================================================================

from server.services.session.manager import SessionManager


class TestSessionManagerMessages:
    def test_add_message(self, fresh_session):
        fresh_session.add_message("user", "hello")
        msgs = fresh_session.get_messages()
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"

    def test_message_cap_at_80(self, fresh_session):
        for i in range(100):
            fresh_session.add_message("user", f"msg{i}")
        msgs = fresh_session.get_messages()
        assert len(msgs) == 80
        # Oldest messages dropped
        assert msgs[0]["content"] == "msg20"

    def test_clear_messages(self, fresh_session):
        fresh_session.add_message("user", "hello")
        fresh_session.clear_messages()
        assert fresh_session.get_messages() == []


class TestSessionManagerStatus:
    def test_initial_status_idle(self, fresh_session):
        assert fresh_session.get_status() == "idle"

    def test_set_status(self, fresh_session):
        fresh_session.set_status("executing")
        assert fresh_session.get_status() == "executing"


class TestSessionManagerPlan:
    def _make_plan(self, num_steps=3):
        return {
            "goal": "Test task",
            "steps": [
                {"id": f"s{i}", "title": f"Step {i}", "instruction": f"Do {i}", "status": "pending"}
                for i in range(num_steps)
            ],
            "current_step_index": 0,
            "status": "active",
        }

    def test_set_and_get_plan(self, fresh_session):
        plan = self._make_plan()
        fresh_session.set_active_plan(plan)
        assert fresh_session.get_active_plan() is not None

    def test_get_current_step(self, fresh_session):
        plan = self._make_plan()
        plan["steps"][0]["status"] = "active"
        fresh_session.set_active_plan(plan)
        step = fresh_session.get_current_step()
        assert step["title"] == "Step 0"

    def test_get_current_step_none_when_no_plan(self, fresh_session):
        assert fresh_session.get_current_step() is None

    def test_complete_step_advances(self, fresh_session):
        plan = self._make_plan()
        plan["steps"][0]["status"] = "active"
        fresh_session.set_active_plan(plan)
        fresh_session.complete_current_step()
        step = fresh_session.get_current_step()
        assert step["title"] == "Step 1"
        assert step["status"] == "active"

    def test_complete_last_step_finishes_plan(self, fresh_session):
        plan = self._make_plan(num_steps=1)
        plan["steps"][0]["status"] = "active"
        fresh_session.set_active_plan(plan)
        fresh_session.complete_current_step()
        assert fresh_session.get_active_plan()["status"] == "completed"
        assert fresh_session.get_status() == "idle"

    def test_go_to_previous_step(self, fresh_session):
        plan = self._make_plan()
        plan["current_step_index"] = 1
        plan["steps"][1]["status"] = "active"
        fresh_session.set_active_plan(plan)
        fresh_session.go_to_previous_step()
        assert fresh_session.get_current_step()["title"] == "Step 0"

    def test_go_to_previous_at_start_does_nothing(self, fresh_session):
        plan = self._make_plan()
        fresh_session.set_active_plan(plan)
        fresh_session.go_to_previous_step()
        assert fresh_session.get_current_step_index() == 0

    def test_skip_current_step(self, fresh_session):
        plan = self._make_plan()
        plan["steps"][0]["status"] = "active"
        fresh_session.set_active_plan(plan)
        fresh_session.skip_current_step()
        # Step 0 should be skipped
        assert plan["steps"][0]["status"] == "skipped"
        assert fresh_session.get_current_step()["title"] == "Step 1"

    def test_skip_last_step_finishes(self, fresh_session):
        plan = self._make_plan(num_steps=1)
        plan["steps"][0]["status"] = "active"
        fresh_session.set_active_plan(plan)
        fresh_session.skip_current_step()
        assert plan["status"] == "completed"


class TestSessionManagerPointer:
    def test_set_and_get_pointer(self, fresh_session):
        ptr = {"x": 500, "y": 300, "label": "Button"}
        fresh_session.set_last_pointer(ptr)
        assert fresh_session.get_last_pointer()["x"] == 500


class TestSessionManagerEvaluations:
    def test_add_evaluation(self, fresh_session):
        fresh_session.add_evaluation({"status": "done", "confidence": 0.9})
        snap = fresh_session.get_snapshot()
        assert len(snap["evaluationHistory"]) == 1

    def test_evaluation_cap_at_40(self, fresh_session):
        for i in range(50):
            fresh_session.add_evaluation({"status": "done"})
        snap = fresh_session.get_snapshot()
        assert len(snap["evaluationHistory"]) == 40


class TestSessionManagerReset:
    def test_reset_clears_all_state(self, fresh_session):
        fresh_session.add_message("user", "hello")
        fresh_session.set_status("executing")
        fresh_session.set_active_plan(self._make_plan()) if False else None
        plan = self._make_plan()
        fresh_session.set_active_plan(plan)
        fresh_session.set_last_pointer({"x": 1, "y": 2})
        fresh_session.add_evaluation({"status": "done"})
        fresh_session.reset()
        snap = fresh_session.get_snapshot()
        assert snap["messages"] == []
        assert snap["status"] == "idle"
        assert snap["activePlan"] is None
        assert snap["lastPointer"] is None
        assert snap["evaluationHistory"] == []

    def _make_plan(self, num_steps=3):
        return {
            "goal": "Test task",
            "steps": [
                {"id": f"s{i}", "title": f"Step {i}", "instruction": f"Do {i}", "status": "pending"}
                for i in range(num_steps)
            ],
            "current_step_index": 0,
            "status": "active",
        }


class TestSessionManagerSnapshot:
    def test_snapshot_has_all_fields(self, fresh_session):
        snap = fresh_session.get_snapshot()
        for key in ["sessionId", "messages", "status", "activePlan", "lastPointer",
                     "evaluationHistory", "updatedAt"]:
            assert key in snap


# ============================================================================
# 0.11 Pydantic model validation
# ============================================================================

class TestUIElementModel:
    def test_minimal_construction(self):
        el = UIElement(element_id="5", bbox=[0, 0, 100, 40], element_type="button", confidence=0.9)
        assert el.element_id == "5"
        assert el.text == ""

    def test_full_construction(self):
        el = UIElement(
            element_id="10", bbox=[10, 20, 30, 40], element_type="input",
            text="search", confidence=0.95, center=[20, 30],
            left_elem_ids=["9"], right_elem_ids=["11"],
        )
        assert len(el.left_elem_ids) == 1

    def test_invalid_element_type(self):
        with pytest.raises(ValidationError):
            UIElement(element_id="1", bbox=[0, 0, 10, 10], element_type="invalid_type", confidence=0.5)


class TestExecutedStepModel:
    def test_default_status_is_pending(self):
        es = ExecutedStep(step_index=1, instruction="Click button")
        assert es.status == "pending"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            ExecutedStep(step_index=1, instruction="X", status="running")


class TestProcessResponseModel:
    def test_minimal_construction(self, mock_elements):
        from server.models.schemas import Blueprint, Intent, ProcessResponse

        resp = ProcessResponse(
            task_id="task-1", success=True,
            intent=Intent(category="ui_navigation", summary="test", confidence=0.9, needs_clarification=False),
            ui_elements=mock_elements,
            blueprint=Blueprint(name="test", total_steps=1, current_step=1, state="generated"),
            steps=[],
        )
        assert resp.task_id == "task-1"
        assert resp.redline is None

    def test_redline_present(self, mock_elements):
        from server.models.schemas import Blueprint, Intent, ProcessResponse, RedlineInfo

        resp = ProcessResponse(
            task_id="task-2", success=True,
            intent=Intent(category="operation_guide", summary="test", confidence=0.9, needs_clarification=False),
            ui_elements=mock_elements,
            blueprint=Blueprint(name="test", total_steps=1, current_step=1, state="generated"),
            steps=[],
            redline=RedlineInfo(triggered=True, category="privacy", message="blocked"),
        )
        assert resp.redline.triggered is True
