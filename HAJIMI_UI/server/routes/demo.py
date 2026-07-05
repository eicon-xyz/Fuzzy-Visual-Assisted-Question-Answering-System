"""
HAJIMI Demo API 路由 — 纯视觉 LLM 版本

移除 OmniParser 依赖。截图直接发给多模态 LLM。
"""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Optional

from server.config import settings
from server.models.schemas import (
    ProcessRequest,
    ProcessResponse,
    StepRequest,
    StepResponse,
    ClarifyRequest,
    ClarifyResponse,
    ReportRequest,
    ReportResponse,
    RelocateRequest,
    RelocateResponse,
    InspectRequest,
    InspectResponse,
    HealthResponse,
)
from server.storage.memory import task_store
from server.services.planning.blueprint_engine import BlueprintEngine
from server.services.llm_ai import process_query, get_clarification_question
from server.services.planning.replanner import replan_steps
from server.services.planning.router import relocate_step
from server.services.agent.orchestrator import orchestrator
from server.database.repository import (
    TaskRepository, RedlineRepository, FeedbackRepository, FailureRepository,
)


router = APIRouter(prefix="/api/demo", tags=["Demo Core"])


# ────────────────────────── 认证依赖 ──────────────────────────


def verify_demo_key(x_demo_key: Optional[str] = Header(None)) -> str:
    """校验 Demo Key"""
    if not x_demo_key or x_demo_key != settings.DEMO_KEY:
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


# ═══════════════════════════════════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="服务健康检查",
    description="供前端启动时探测后端是否可用，无需认证。",
)
async def health_check():
    """Health check — no OmniParser probe needed."""
    return HealthResponse(
        status="ok",
        version="1.1.0",
        detector_backend="vision_llm",
        detector_active="vision_llm",
        detector_device="cpu",
        omniparser_url="",
        omniparser_ready=True,  # Always ready — pure vision LLM
    )


@router.post(
    "/process",
    response_model=ProcessResponse,
    summary="核心流程入口",
    description="接收截图与用户问题，返回操作步骤和屏幕标注坐标。纯视觉 LLM 管道。",
)
async def process(
    request: ProcessRequest,
    demo_key: str = Depends(verify_demo_key),
):
    # 1. 调用纯视觉 LLM 管道生成响应
    response = process_query(
        request.query,
        request.image,
        screen_width=getattr(request, 'screen_width', 1920),
        screen_height=getattr(request, 'screen_height', 1080),
    )

    # 2. 红线拦截 → 记录日志，不创建任务
    if response.redline and response.redline.triggered:
        RedlineRepository.log(
            query=request.query,
            category=response.redline.category,
            action=response.redline.action,
            message=response.redline.message,
        )
        return response

    # 3. 成功任务 → 内存 + 数据库双写
    task_store.create(response, request.query)
    TaskRepository.create_from_response(response, request.query)

    return response


@router.post(
    "/inspect",
    response_model=InspectResponse,
    summary="屏幕检测",
    description="使用视觉 LLM 检测当前屏幕元素。",
)
async def inspect(
    request: InspectRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """Screen inspect — uses vision LLM for element detection."""
    # For inspect, we use fast mode chat to ask the vision LLM about the screen
    if request.image and settings.USE_REAL_LLM:
        try:
            result = orchestrator.send_message(
                text="List all visible UI elements on this screen (buttons, inputs, icons, menus, text). "
                     "Return as a JSON array with fields: id, type, text, bbox[x1,y1,x2,y2], center[x,y].",
                image_base64=request.image,
            )
            reply = result.get("spokenText", "")
        except Exception:
            reply = ""
    else:
        reply = ""

    return InspectResponse(
        success=True,
        ui_elements=[],
        annotated_image=request.image,
        reference_resolution=None,
        detection_meta={"backend": "vision_llm", "reply": reply},
    )


@router.post(
    "/step",
    response_model=StepResponse,
    summary="推进蓝图步骤",
    description="用户完成一步后调用，支持 advance/rollback/skip/terminate。",
)
async def step(
    request: StepRequest,
    demo_key: str = Depends(verify_demo_key),
):
    # 1. 查找任务
    state = task_store.get(request.task_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"task_id {request.task_id} 不存在",
                    "details": {},
                }
            },
        )

    # 2. 如果是第一次推进且状态为 pending_confirm，先确认
    if state.blueprint.state == "pending_confirm" and request.action == "advance":
        BlueprintEngine.confirm(state)
        task_store.update(state)
        return StepResponse(
            task_id=state.task_id,
            action="advance",
            current_step=state.blueprint.current_step,
            blueprint_state=state.blueprint.state,
            next_step=state.steps[state.blueprint.current_step - 1],
            message="蓝图已确认，开始执行",
        )

    # 3. 执行状态机操作
    engine = BlueprintEngine()
    message = None

    if request.action == "advance":
        # 如果提供了新截图且启用了评估，执行智能评估
        if request.image and getattr(settings, 'EVALUATOR_ENABLED', False):
            try:
                eval_result = orchestrator.evaluate_current_step(
                    image_base64=request.image,
                    screen_width=getattr(request, 'screen_width', 1920),
                    screen_height=getattr(request, 'screen_height', 1080),
                )
                eval_action = eval_result.get("action", "advance")

                if eval_action == "repeat_guidance":
                    evaluation = eval_result.get("evaluation", {})
                    return StepResponse(
                        task_id=state.task_id,
                        action="advance",
                        current_step=state.blueprint.current_step,
                        blueprint_state=state.blueprint.state,
                        next_step=state.steps[state.blueprint.current_step - 1],
                        message=f"步骤可能未完成。{evaluation.get('rationale', '请再试一次。')}",
                    )

                if eval_action == "replan":
                    # Replan was done by orchestrator — update state
                    session = eval_result.get("session", {})
                    plan = session.get("activePlan", {})
                    if plan and plan.get("steps"):
                        # Convert orchestrator steps back to state
                        pass  # Keep existing state, orchestrator handles its own session
            except Exception:
                pass  # Fall through to normal advance

        action, next_step = engine.advance(state, settings.STRICT_FINGERPRINT)
        if action == "complete":
            message = "任务已完成"

        # 动态重规划：如果步骤缺少 target_element_id
        if (
            action == "advance"
            and next_step
            and not next_step.target_element_id
        ):
            # Pure vision replan — no OmniParser dependency
            pass

    elif request.action == "rollback":
        action, next_step = engine.rollback(state)
        message = "已回退一步"
    elif request.action == "skip":
        action, next_step = engine.skip(state)
        message = "已跳过当前步骤"
    elif request.action == "terminate":
        action = engine.terminate(state)
        next_step = None
        message = "任务已终止"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": f"不支持的 action: {request.action}",
                    "details": {},
                }
            },
        )

    # 4. 更新状态
    state.fingerprint = request.fingerprint
    task_store.update(state)

    return StepResponse(
        task_id=state.task_id,
        action=action,
        current_step=state.blueprint.current_step,
        blueprint_state=state.blueprint.state,
        next_step=next_step,
        message=message,
    )


@router.post(
    "/relocate",
    response_model=RelocateResponse,
    summary="重新定位步骤",
    description="当前画面找不到目标元素时，用户手动完成操作后上传新截图重新定位。",
)
async def relocate(
    request: RelocateRequest,
    demo_key: str = Depends(verify_demo_key),
):
    # 1. 查找任务
    state = task_store.get(request.task_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"task_id {request.task_id} 不存在",
                    "details": {},
                }
            },
        )

    # 2. 查找目标步骤
    step_index = request.step_index
    if step_index < 1 or step_index > len(state.steps):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_STEP_INDEX",
                    "message": f"step_index {step_index} 超出范围 (1–{len(state.steps)})",
                    "details": {},
                }
            },
        )

    target_step = state.steps[step_index - 1]

    # 3. 对新截图重定位（纯视觉 LLM）
    target_element_id, annotation, elements = relocate_step(
        step_action=target_step.action,
        step_description=target_step.description,
        image_base64=request.image,
        screen_width=getattr(request, 'screen_width', 1920),
        screen_height=getattr(request, 'screen_height', 1080),
    )

    # 4. 更新步骤绑定
    if target_element_id:
        target_step.target_element_id = target_element_id
        target_step.annotation = annotation
        target_step.status = "active"

    # 5. 持久化
    task_store.update(state)

    return RelocateResponse(
        success=bool(target_element_id),
        task_id=state.task_id,
        step_index=step_index,
        target_element_id=target_element_id,
        annotation=annotation,
        ui_elements=elements,
    )


@router.post(
    "/clarify",
    response_model=ClarifyResponse,
    summary="主动澄清应答",
)
async def clarify(
    request: ClarifyRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """Clarify user intent."""
    state = task_store.get(request.task_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"task_id {request.task_id} 不存在",
                    "details": {},
                }
            },
        )

    new_confidence = min(state.intent.confidence + 0.1, 0.95)
    state.intent.confidence = new_confidence
    state.intent.needs_clarification = new_confidence < 0.80

    question = None
    if state.intent.needs_clarification:
        question = get_clarification_question(state.intent)

    task_store.update(state)

    return ClarifyResponse(
        task_id=state.task_id,
        confidence=new_confidence,
        needs_clarification=state.intent.needs_clarification,
        question=question,
        updated_intent=state.intent,
    )


@router.post(
    "/report",
    response_model=ReportResponse,
    summary="审计与反馈上报",
)
async def report(
    request: ReportRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """Audit and feedback submission."""
    from loguru import logger

    state = task_store.get(request.task_id)

    logger.info(
        "audit_report | task_id={} | query={} | result={} | feedback={} | duration_ms={}",
        request.task_id,
        state.query if state else "unknown",
        request.result,
        request.feedback_type,
        request.duration_ms,
    )

    if request.feedback_type:
        FeedbackRepository.create(
            task_id=request.task_id,
            feedback_type=request.feedback_type,
            comment=request.comment,
        )
    if request.result:
        TaskRepository.update_result(
            task_id=request.task_id,
            result=request.result,
            duration_ms=request.duration_ms,
        )

    return ReportResponse(received=True)


# ═══════════════════════════════════════════════════════════════════════════
# 新增端点
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/evaluate",
    summary="步骤评估",
    description="评估当前步骤是否已完成的智能检查。",
)
async def evaluate(
    task_id: str = Header(..., alias="X-Task-Id"),
    image: Optional[str] = None,
    demo_key: str = Depends(verify_demo_key),
):
    """Evaluate current step completion with vision LLM."""
    try:
        result = orchestrator.evaluate_current_step(
            image_base64=image,
            screen_width=1920,
            screen_height=1080,
        )
        return {"success": True, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post(
    "/cancel",
    summary="取消任务",
    description="取消当前进行中的任务。",
)
async def cancel(
    task_id: str = Header(..., alias="X-Task-Id"),
    demo_key: str = Depends(verify_demo_key),
):
    """Cancel the current task."""
    orchestrator.cancel_plan()
    # Also clean up task_store
    state = task_store.get(task_id)
    if state:
        BlueprintEngine().terminate(state)
        task_store.update(state)
    return {"success": True, "message": "Task cancelled"}
