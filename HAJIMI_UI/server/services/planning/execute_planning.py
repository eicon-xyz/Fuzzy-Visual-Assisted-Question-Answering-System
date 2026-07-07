"""
L5 执行路径规划 — 红线 → 意图 → Planning Agent → 可选首帧 OmniParser

与 L3/L4 指引路径的 process_query 分离，供 POST /execute 使用。
"""

from __future__ import annotations

import concurrent.futures
import logging
import uuid
from typing import List, Optional

from server.models.schemas import (
    Blueprint,
    Intent,
    ProcessResponse,
    RedlineInfo,
    Step,
    UIElement,
)
from server.services.llm_ai import classify_intent, detect_reference_type
from server.services.planning.planner import PlanningResult, plan_steps
from server.services.redline_service import check_redline

logger = logging.getLogger(__name__)


def plan_for_execute(
    query: str,
    image_base64: Optional[str] = None,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> ProcessResponse:
    """Planning phase for L5 auto-execution."""
    redline = check_redline(query)
    if redline.triggered:
        return ProcessResponse(
            task_id=str(uuid.uuid4()),
            success=False,
            goal="",
            intent=Intent(
                category="operation_guide",
                summary="请求被拦截",
                reference_type="explicit",
                confidence=1.0,
                needs_clarification=False,
            ),
            ui_elements=[],
            annotated_image=None,
            blueprint=Blueprint(
                name="红线拦截",
                total_steps=1,
                current_step=1,
                state="terminated",
            ),
            steps=[],
            redline=RedlineInfo(
                triggered=True,
                category=redline.category,
                message=redline.message,
                action=redline.action,
            ),
            detection_meta={"route": "L5"},
        )

    category, summary, confidence = classify_intent(query)
    reference_type = detect_reference_type(query)
    intent = Intent(
        category=category,
        summary=summary,
        reference_type=reference_type,
        confidence=confidence,
        needs_clarification=confidence < 0.80,
    )

    plan_result: PlanningResult | None = None

    def _call_planner() -> None:
        nonlocal plan_result
        try:
            plan_result = plan_steps(query)
        except Exception as exc:
            logger.error("Planning Agent failed: %s", exc)
            from server.models.schemas import PlanningStep

            plan_result = PlanningResult(
                goal=query,
                steps=[PlanningStep(step_index=1, instruction=query)],
            )

    ui_elements: List[UIElement] = []
    annotated_image: Optional[str] = image_base64
    detection_meta: dict = {"backend": "omniparser", "route": "L5"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        planner_future = executor.submit(_call_planner)
        if image_base64:
            try:
                from server.services.omniparser_client import parse_screenshot_full

                parse_result = parse_screenshot_full(image_base64)
                ui_elements = parse_result.elements
                annotated_image = parse_result.annotated_image or image_base64
                detection_meta.update(parse_result.detection_meta or {})
            except Exception as exc:
                logger.error("OmniParser initial scan failed: %s", exc)
        planner_future.result(timeout=60)

    assert plan_result is not None
    goal = plan_result.goal
    steps = [
        Step(
            step_index=ps.step_index,
            action="execute",
            description=ps.instruction,
            status="pending",
        )
        for ps in plan_result.steps
    ]

    blueprint = Blueprint(
        name=(goal[:40] if goal else summary),
        total_steps=len(steps),
        current_step=1,
        state="generated",
    )

    return ProcessResponse(
        task_id=str(uuid.uuid4()),
        success=True,
        goal=goal,
        intent=intent,
        ui_elements=ui_elements,
        annotated_image=annotated_image,
        blueprint=blueprint,
        steps=steps,
        detection_meta=detection_meta,
    )
