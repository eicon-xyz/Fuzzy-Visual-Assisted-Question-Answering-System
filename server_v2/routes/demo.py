"""
HAJIMI Demo API routes — updated to use TaskOrchestrator (OpenGuider-style PEER loop).

Backward compatible with the original API contract (api-contract-demo.md).
All 7 endpoints preserved: health, process, inspect, step, relocate, clarify, report.

Key changes:
- /process now uses TaskOrchestrator.start_goal_session() with local perception
- /step now uses TaskOrchestrator peer-loop methods
- /inspect now uses local perception (OCR + UIA) instead of OmniParser
- /health reports local perception status instead of OmniParser
- Falls back to original OmniParser pipeline if orchestrator unavailable
"""

from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Optional

router = APIRouter(prefix="/api/demo", tags=["Demo Core"])

# ── Global orchestrator reference (set by main.py at startup) ──

_orchestrator = None
_settings = None


def init_demo_routes(orchestrator, settings):
    """Initialize with the TaskOrchestrator instance from main.py."""
    global _orchestrator, _settings
    _orchestrator = orchestrator
    _settings = settings


# ── Auth dependency ──────────────────────────────────────────────────────────


def verify_demo_key(x_demo_key: Optional[str] = Header(None)) -> str:
    if _settings and x_demo_key and x_demo_key == _settings.DEMO_KEY:
        return x_demo_key
    if not x_demo_key or (_settings and x_demo_key != _settings.DEMO_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_FAILED",
                    "message": "X-Demo-Key 无效",
                    "details": {},
                }
            },
        )
    return x_demo_key


# ── Legacy imports (fallback when orchestrator unavailable) ──────────────────

def _get_legacy_modules():
    """Lazy-import legacy modules for fallback compatibility."""
    from server_v2.config import settings
    from server_v2.storage.memory import task_store
    from server_v2.services.planning.blueprint_engine import BlueprintEngine
    from server_v2.services.llm_ai import process_query, get_clarification_question
    from server_v2.services.omniparser_client import parse_screenshot, parse_screenshot_full
    from server_v2.services.planning.replanner import replan_steps
    from server_v2.services.planning.router import relocate_step
    from server_v2.database.repository import (
        TaskRepository, RedlineRepository, FeedbackRepository, FailureRepository,
    )
    return {
        "settings": settings,
        "task_store": task_store,
        "BlueprintEngine": BlueprintEngine,
        "process_query": process_query,
        "get_clarification_question": get_clarification_question,
        "parse_screenshot": parse_screenshot,
        "parse_screenshot_full": parse_screenshot_full,
        "replan_steps": replan_steps,
        "relocate_step": relocate_step,
        "TaskRepository": TaskRepository,
        "RedlineRepository": RedlineRepository,
        "FeedbackRepository": FeedbackRepository,
        "FailureRepository": FailureRepository,
    }


# ────────────────────────── Routes ──────────────────────────


@router.get("/health", summary="服务健康检查")
async def health_check():
    """Health check — reports local perception status instead of OmniParser."""
    perception_ready = False
    ocr_ready = False

    # Check OCR
    try:
        from perception.ocr_engine import get_ocr_engine
        engine = get_ocr_engine()
        ocr_ready = engine.available
    except Exception:
        pass

    # Check UIA
    try:
        from perception.ui_scanner import query_ui_automation
        elements = query_ui_automation(max_elements=1)
        perception_ready = True  # Even empty list means the API works
    except Exception:
        pass

    from server_v2.models.schemas import HealthResponse
    return HealthResponse(
        status="ok",
        version="2.0.0",
        detector_backend="local_perception" if perception_ready else "fallback_ocr",
        omniparser_ready=perception_ready,  # Keep field name for backward compat
    )


@router.post("/process", summary="核心流程入口")
async def process(request, demo_key: str = Depends(verify_demo_key)):
    """Core process endpoint — now powered by TaskOrchestrator PEER loop."""
    from server_v2.models.schemas import ProcessRequest, ProcessResponse
    from server_v2.models.schemas import ProcessResponse

    query = request.query
    image_b64 = request.image

    # Try orchestrator first
    if _orchestrator:
        try:
            images = [{"base64Jpeg": image_b64}] if image_b64 else []
            result = await _orchestrator.start_goal_session(
                text=query,
                images=images,
                settings=_settings,
            )

            plan = result.get("plan", {})
            guide = result.get("guide_result", {})
            session = result.get("session", {})

            # Build backward-compatible response
            steps = []
            for s in plan.get("steps", []):
                from server_v2.models.schemas import Step as StepModel
                steps.append(StepModel(
                    step_index=s.get("id", "").replace("step_", ""),
                    action=s.get("title", ""),
                    description=s.get("instruction", ""),
                    target_element_id=None,
                    status=s.get("status", "pending"),
                    annotation=None,
                    risk_score=s.get("risk_score", 2),
                ))

            from server_v2.models.schemas import (
                ProcessResponse, Blueprint, Intent,
            )
            return ProcessResponse(
                task_id=session.get("session_id", ""),
                intent=Intent(
                    category="guide",
                    summary=plan.get("goal", query),
                    confidence=0.85,
                    needs_clarification=False,
                ),
                ui_elements=[],
                annotated_image="",
                blueprint=Blueprint(
                    name=plan.get("goal", ""),
                    total_steps=len(steps),
                    current_step=plan.get("current_step_index", 0) + 1,
                    state=plan.get("status", "pending_confirm"),
                ),
                steps=steps,
                constraints=[],
                reference_resolution={"width": 1920, "height": 1080},
                detection_meta={"detector": "local_perception", "element_count": 0},
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Orchestrator fell back to legacy: {e}"
            )

    # Fallback: legacy OmniParser pipeline
    mods = _get_legacy_modules()
    response = mods["process_query"](query, image_b64)

    if response.redline and response.redline.triggered:
        mods["RedlineRepository"].log(
            query=query,
            category=response.redline.category,
            action=response.redline.action,
            message=response.redline.message,
        )
        return response

    mods["task_store"].create(response, query)
    mods["TaskRepository"].create_from_response(response, query)
    return response


@router.post("/inspect", summary="立即检测当前屏幕")
async def inspect(request, demo_key: str = Depends(verify_demo_key)):
    """Inspect screen — now uses local perception (OCR + UIA)."""
    from server_v2.models.schemas import InspectRequest, InspectResponse

    # Try local perception
    try:
        from perception.ocr_engine import get_ocr_engine
        from perception.ui_scanner import query_ui_automation
        from perception.window_enum import enumerate_active_app

        elements = []
        image_b64 = request.image

        if image_b64:
            # OCR
            engine = get_ocr_engine()
            ocr_result = engine.recognize_from_base64(image_b64)

            # UIA
            uia_elements = query_ui_automation(max_elements=500)

            # Convert to UIElement format
            from server_v2.models.schemas import UIElement
            for i, el in enumerate(uia_elements[:50]):
                center_x = el.rect.get("x", 0) + el.rect.get("width", 0) // 2
                center_y = el.rect.get("y", 0) + el.rect.get("height", 0) // 2
                elements.append(UIElement(
                    element_id=f"~{i + 1}",
                    bbox=[
                        el.rect.get("x", 0),
                        el.rect.get("y", 0),
                        el.rect.get("x1", el.rect.get("width", 0)),
                        el.rect.get("y1", el.rect.get("height", 0)),
                    ],
                    element_type=el.control_type or "control",
                    text=el.name,
                    confidence=0.9,
                    center=[center_x, center_y],
                ))

        return InspectResponse(
            ui_elements=elements,
            annotated_image="",  # No SoM annotation in local mode
            reference_resolution={"width": 1920, "height": 1080},
            detection_meta={
                "detector": "local_perception",
                "element_count": len(elements),
                "ocr_words": len(ocr_result.words) if ocr_result else 0,
            },
        )
    except Exception as e:
        # Fallback to OmniParser
        mods = _get_legacy_modules()
        result = mods["parse_screenshot_full"](request.image)
        return InspectResponse(
            ui_elements=result.elements,
            annotated_image=result.annotated_image,
            reference_resolution=result.reference_resolution,
            detection_meta=result.detection_meta,
        )


@router.post("/step", summary="推进蓝图步骤")
async def step(request, demo_key: str = Depends(verify_demo_key)):
    """Step advancement — delegates to orchestrator or legacy BlueprintEngine."""
    from server_v2.models.schemas import StepRequest, StepResponse

    # Try orchestrator
    if _orchestrator:
        action = request.action
        if action == "advance":
            result = await _orchestrator.mark_step_done(
                settings=_settings,
            )
        elif action == "skip":
            result = await _orchestrator.skip_current_step()
        elif action == "rollback":
            result = await _orchestrator.previous_step()
        elif action == "terminate":
            result = _orchestrator.cancel_active_plan()
        else:
            raise HTTPException(status_code=400, detail={
                "error": {"code": "INVALID_REQUEST", "message": f"不支持 action: {action}"}
            })

        session = _orchestrator.get_snapshot()
        plan = session.get("active_plan", {}) or {}

        return StepResponse(
            task_id=session.get("session_id", ""),
            action=action,
            current_step=(plan.get("current_step_index", 0) + 1) if plan else 0,
            blueprint_state=plan.get("status", "idle"),
            next_step=None,
            message=result.get("action", "ok"),
        )

    # Fallback: legacy
    mods = _get_legacy_modules()
    state = mods["task_store"].get(request.task_id)
    if not state:
        raise HTTPException(status_code=404, detail={
            "error": {"code": "NOT_FOUND", "message": f"task_id {request.task_id} 不存在"}
        })

    engine = mods["BlueprintEngine"]()
    if request.action == "advance":
        act, next_step = engine.advance(state, False)
    elif request.action == "rollback":
        act, next_step = engine.rollback(state)
    elif request.action == "skip":
        act, next_step = engine.skip(state)
    elif request.action == "terminate":
        act = engine.terminate(state)
        next_step = None
    else:
        raise HTTPException(status_code=400, detail={
            "error": {"code": "INVALID_REQUEST", "message": f"不支持 action: {request.action}"}
        })

    mods["task_store"].update(state)
    return StepResponse(
        task_id=state.task_id,
        action=act,
        current_step=state.blueprint.current_step,
        blueprint_state=state.blueprint.state,
        next_step=next_step,
        message="ok",
    )


@router.post("/relocate", summary="重新定位步骤")
async def relocate(request, demo_key: str = Depends(verify_demo_key)):
    """Relocate — delegates to orchestrator regenerate or legacy."""
    from server_v2.models.schemas import RelocateRequest, RelocateResponse

    if _orchestrator:
        result = await _orchestrator.regenerate_current_step(settings=_settings)
        session = _orchestrator.get_snapshot()
        pointer = session.get("last_pointer", {}) or {}
        return RelocateResponse(
            task_id=session.get("session_id", ""),
            step_index=request.step_index,
            target_element_id=None,
            annotation=None,
            ui_elements=[],
        )

    # Fallback: legacy
    mods = _get_legacy_modules()
    state = mods["task_store"].get(request.task_id)
    if not state:
        raise HTTPException(status_code=404, detail={
            "error": {"code": "NOT_FOUND", "message": f"task_id {request.task_id} 不存在"}
        })

    target_id, annotation, elements = mods["relocate_step"](
        step_action=state.steps[request.step_index - 1].action,
        step_description=state.steps[request.step_index - 1].description,
        image_base64=request.image,
    )
    mods["task_store"].update(state)
    return RelocateResponse(
        task_id=state.task_id,
        step_index=request.step_index,
        target_element_id=target_id,
        annotation=annotation,
        ui_elements=elements,
    )


@router.post("/clarify", summary="主动澄清应答")
async def clarify(request, demo_key: str = Depends(verify_demo_key)):
    """Clarify — legacy only for now."""
    from server_v2.models.schemas import ClarifyRequest, ClarifyResponse
    mods = _get_legacy_modules()
    state = mods["task_store"].get(request.task_id)
    if not state:
        raise HTTPException(status_code=404, detail={
            "error": {"code": "NOT_FOUND", "message": f"task_id {request.task_id} 不存在"}
        })

    new_conf = min(state.intent.confidence + 0.1, 0.95)
    state.intent.confidence = new_conf
    state.intent.needs_clarification = new_conf < 0.80

    question = None
    if state.intent.needs_clarification:
        question = mods["get_clarification_question"](state.intent)

    mods["task_store"].update(state)
    return ClarifyResponse(
        task_id=state.task_id,
        confidence=new_conf,
        needs_clarification=state.intent.needs_clarification,
        question=question,
        updated_intent=state.intent,
    )


@router.post("/report", summary="审计与反馈上报")
async def report(request, demo_key: str = Depends(verify_demo_key)):
    """Report — unchanged."""
    from server_v2.models.schemas import ReportRequest, ReportResponse
    from loguru import logger
    mods = _get_legacy_modules()

    state = mods["task_store"].get(request.task_id)
    logger.info(
        "audit_report | task_id={} | query={} | result={} | feedback={} | duration_ms={}",
        request.task_id,
        state.query if state else "unknown",
        request.result,
        request.feedback_type,
        request.duration_ms,
    )

    if request.feedback_type:
        mods["FeedbackRepository"].create(
            task_id=request.task_id,
            feedback_type=request.feedback_type,
            comment=request.comment,
        )
    if request.result:
        mods["TaskRepository"].update_result(
            task_id=request.task_id,
            result=request.result,
            duration_ms=request.duration_ms,
        )

    return ReportResponse(received=True)
