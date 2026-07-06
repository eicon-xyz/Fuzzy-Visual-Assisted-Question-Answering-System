"""
Tests for server/models/schemas.py — Task 1: Data Model Changes

Verifies new spatial relations on UIElement, new PlanningStep/ExecutedStep models,
simplified Blueprint states, and ProcessResponse changes.
"""

import pytest
from server.models.schemas import (
    UIElement,
    PlanningStep,
    ExecutedStep,
    Blueprint,
    ProcessResponse,
    Intent,
)


def test_uielement_has_spatial_relations():
    el = UIElement(
        element_id="5",
        bbox=[100, 200, 300, 400],
        element_type="button",
        text="search",
        confidence=0.95,
        center=[200, 300],
        left_elem_ids=["3", "4"],
        right_elem_ids=["6"],
        top_elem_ids=["1"],
        bottom_elem_ids=["8", "9"],
    )
    assert el.left_elem_ids == ["3", "4"]
    assert el.right_elem_ids == ["6"]
    assert el.top_elem_ids == ["1"]
    assert el.bottom_elem_ids == ["8", "9"]


def test_uielement_spatial_defaults_empty():
    el = UIElement(
        element_id="1",
        bbox=[0, 0, 10, 10],
        element_type="text",
        text="",
        confidence=0.5,
        center=[5, 5],
    )
    assert el.left_elem_ids == []
    assert el.right_elem_ids == []
    assert el.top_elem_ids == []
    assert el.bottom_elem_ids == []


def test_planning_step():
    ps = PlanningStep(step_index=1, instruction="open the app")
    assert ps.step_index == 1
    assert ps.instruction == "open the app"


def test_planning_step_rejects_zero_index():
    with pytest.raises(ValueError):
        PlanningStep(step_index=0, instruction="invalid")


def test_executed_step_defaults():
    es = ExecutedStep(step_index=2, instruction="click search")
    assert es.action is None
    assert es.target_element_id is None
    assert es.params is None
    assert es.action_summary is None
    assert es.status == "pending"


def test_executed_step_status_pattern():
    for valid_status in ["pending", "executing", "done", "failed"]:
        es = ExecutedStep(step_index=1, instruction="x", status=valid_status)
        assert es.status == valid_status

    with pytest.raises(ValueError):
        ExecutedStep(step_index=1, instruction="x", status="invalid")


def test_blueprint_states_no_pending_confirm():
    bp = Blueprint(name="test", total_steps=3, current_step=1, state="executing")
    assert bp.state == "executing"

    # Verify all legacy states are now valid
    bp2 = Blueprint(name="x", total_steps=1, current_step=1, state="pending_confirm")
    assert bp2.state == "pending_confirm"
    bp3 = Blueprint(name="x", total_steps=1, current_step=1, state="suspended")
    assert bp3.state == "suspended"
    bp4 = Blueprint(name="x", total_steps=1, current_step=1, state="rolling_back")
    assert bp4.state == "rolling_back"


def test_blueprint_rejects_invalid_state():
    with pytest.raises(ValueError):
        Blueprint(name="x", total_steps=1, current_step=1, state="made_up")


def test_blueprint_valid_states():
    for state in ["generated", "executing", "completed", "terminated"]:
        bp = Blueprint(name="x", total_steps=1, current_step=1, state=state)
        assert bp.state == state


def test_process_response_has_goal_no_reference_resolution():
    intent = Intent(
        category="operation_guide",
        summary="test",
        reference_type="explicit",
        confidence=1.0,
        needs_clarification=False,
    )
    pr = ProcessResponse(
        task_id="t1",
        success=True,
        goal="do the thing",
        intent=intent,
        steps=[],
        ui_elements=[],
        blueprint=Blueprint(name="b", total_steps=1, current_step=1, state="generated"),
    )
    assert pr.goal == "do the thing"
    assert not hasattr(pr, "reference_resolution")
    assert not hasattr(pr, "constraints")


def test_process_response_has_redline():
    from server.models.schemas import RedlineInfo

    intent = Intent(
        category="operation_guide",
        summary="test",
        reference_type="explicit",
        confidence=1.0,
        needs_clarification=False,
    )
    redline = RedlineInfo(triggered=True, category="danger", message="stop!")
    pr = ProcessResponse(
        task_id="t1",
        success=True,
        goal="test",
        intent=intent,
        steps=[],
        ui_elements=[],
        blueprint=Blueprint(name="b", total_steps=1, current_step=1, state="generated"),
        redline=redline,
    )
    assert pr.redline is not None
    assert pr.redline.triggered is True
    assert pr.redline.category == "danger"


def test_step_class_still_exists():
    """Old Step class must remain for backward compatibility."""
    from server.models.schemas import Step

    s = Step(step_index=1, action="click", description="do it", status="pending")
    assert s.step_index == 1
