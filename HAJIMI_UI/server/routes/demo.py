"""
HAJIMI Demo API 路由
实现 api-contract-demo.md 中定义的全部端点
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
    ErrorResponse,
    Intent,
)
from server.storage.memory import task_store
from server.services.planning.blueprint_engine import BlueprintEngine
from server.services.llm_ai import process_query, get_clarification_question
from server.services.omniparser_client import parse_screenshot, parse_screenshot_full
from server.services.planning.replanner import replan_steps
from server.services.planning.router import relocate_step
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


# ────────────────────────── 路由 ──────────────────────────


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="服务健康检查",
    description="供前端启动时探测后端是否可用，无需认证。",
)
async def health_check():
    omniparser_ready = False
    detector_device = None
    omni_url = settings.OMNIPARSER_URL.rstrip("/")
    try:
        import httpx
        with httpx.Client(timeout=3) as client:
            r = client.get(omni_url)
            omniparser_ready = r.status_code < 500
            if omniparser_ready:
                try:
                    probe = client.get(f"{omni_url}/probe/", timeout=3)
                    if probe.status_code == 200:
                        body = probe.json()
                        if isinstance(body, dict):
                            detector_device = body.get("device")
                except Exception:
                    pass
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        version="1.0.0",
        detector_backend="local_omniparser",
        detector_active="local_omniparser",
        detector_device=detector_device or "cpu",
        omniparser_url=omni_url,
        omniparser_ready=omniparser_ready,
    )


@router.post(
    "/process",
    response_model=ProcessResponse,
    summary="核心流程入口",
    description="接收截图与用户问题，返回操作步骤和屏幕标注坐标。",
)
async def process(
    request: ProcessRequest,
    demo_key: str = Depends(verify_demo_key),
):
    # 1. 调用 AI 服务生成响应（传入截图供本地 OmniParser 解析）
    response = process_query(request.query, request.image)

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
    summary="立即检测当前屏幕",
    description="仅检测 UI 元素，不生成 task/steps。供 Settings「立即检测当前屏幕」使用。",
)
async def inspect(
    request: InspectRequest,
    demo_key: str = Depends(verify_demo_key),
):
    result = parse_screenshot_full(request.image)

    return InspectResponse(
        success=True,
        ui_elements=result.elements,
        annotated_image=result.annotated_image,
        reference_resolution=result.reference_resolution,
        detection_meta=result.detection_meta,
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
        action, next_step = engine.advance(state, settings.STRICT_FINGERPRINT)
        if action == "complete":
            message = "任务已完成"

        # === 动态重规划 ===
        if (
            action == "advance"
            and request.image
            and next_step
            and not next_step.target_element_id
        ):
            new_elements = parse_screenshot(request.image)
            if new_elements:
                updated_steps = replan_steps(
                    original_query=state.query,
                    current_step_index=state.blueprint.current_step - 1,
                    all_steps=state.steps,
                    new_elements=new_elements,
                )
                for i, updated in enumerate(updated_steps):
                    if state.blueprint.current_step - 1 <= i < len(state.steps):
                        state.steps[i] = updated
                next_step = state.steps[state.blueprint.current_step - 1]
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

    # 3. 对新截图重定位
    target_element_id, annotation, elements = relocate_step(
        step_action=target_step.action,
        step_description=target_step.description,
        image_base64=request.image,
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
    description="当 process 返回 needs_clarification=true 时，用户回答后调用。",
)
async def clarify(
    request: ClarifyRequest,
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

    # 2. Demo 阶段简化：根据回答重新生成意图
    # 实际应结合上下文做指代消解，这里简化为置信度提升
    new_confidence = min(state.intent.confidence + 0.1, 0.95)
    state.intent.confidence = new_confidence
    state.intent.needs_clarification = new_confidence < 0.80

    # 3. 如果仍然不够清晰，生成新问题
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
    description="任务结束后异步上报结果和反馈，Demo 阶段仅记录日志。",
)
async def report(
    request: ReportRequest,
    demo_key: str = Depends(verify_demo_key),
):
    from loguru import logger

    # 1. 查找任务（可选）
    state = task_store.get(request.task_id)

    # 2. 记录日志
    logger.info(
        "audit_report | task_id={} | query={} | result={} | feedback={} | duration_ms={}",
        request.task_id,
        state.query if state else "unknown",
        request.result,
        request.feedback_type,
        request.duration_ms,
    )

    # 3. 持久化反馈 + 更新任务结果
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
