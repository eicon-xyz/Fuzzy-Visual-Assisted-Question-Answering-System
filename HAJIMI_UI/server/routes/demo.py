"""
HAJIMI Demo API 路由
实现 api-contract-demo.md 中定义的全部端点
"""
import httpx
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
    HealthResponse,
    InspectRequest,
    InspectResponse,
    RelocateRequest,
    RelocateResponse,
    Intent,
)
from server.storage.memory import task_store
from server.services.blueprint import BlueprintEngine
from server.services.llm_ai import (
    process_query,
    inspect_image,
    get_clarification_question,
    relocate_step_on_screen,
)
from server.services.image_utils import decode_image
from server.services.ui_detector import DetectorError


router = APIRouter(prefix="/api/demo", tags=["Demo Core"])


def _probe_omniparser() -> bool:
    base_url = (settings.OMNIPARSER_LOCAL_URL or "").rstrip("/")
    if not base_url:
        return False
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{base_url}/probe/")
            return resp.status_code == 200
    except Exception:
        return False


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
    omniparser_ready = None
    if settings.DETECTOR_BACKEND == "local_omniparser":
        omniparser_ready = _probe_omniparser()
    return HealthResponse(
        status="ok",
        version="1.0.0",
        detector_backend=settings.DETECTOR_BACKEND,
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
    if settings.REQUIRE_IMAGE and not request.image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MISSING_IMAGE",
                    "message": "缺少 screenshot image",
                    "details": {},
                }
            },
        )

    try:
        response = process_query(request.query, image_b64=request.image)
    except ValueError as exc:
        code = str(exc)
        if code == "NO_ELEMENTS_DETECTED":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": code,
                        "message": "未检测到 UI 元素",
                        "details": {},
                    }
                },
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {"code": code, "message": str(exc), "details": {}},
            },
        ) from exc
    except DetectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "DETECTOR_FAILED",
                    "message": str(exc),
                    "details": {},
                }
            },
        ) from exc

    task_store.create(response, request.query)
    return response


@router.post(
    "/inspect",
    response_model=InspectResponse,
    summary="元素检测检验",
    description="仅检测截图中的 UI 元素并返回 SoM 标注，不生成任务步骤。",
)
async def inspect(
    request: InspectRequest,
    demo_key: str = Depends(verify_demo_key),
):
    if not request.image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MISSING_IMAGE",
                    "message": "缺少 screenshot image",
                    "details": {},
                }
            },
        )

    try:
        pil, w, h = decode_image(request.image)
        print(
            f"[inspect] received image {w}x{h} "
            f"detector={settings.DETECTOR_BACKEND} "
            f"omniparser_url={settings.OMNIPARSER_LOCAL_URL}"
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {"code": "INVALID_IMAGE", "message": str(exc), "details": {}},
            },
        ) from exc

    try:
        return inspect_image(request.image)
    except ValueError as exc:
        if str(exc) == "NO_ELEMENTS_DETECTED":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "NO_ELEMENTS_DETECTED",
                        "message": "未检测到 UI 元素",
                        "details": {},
                    }
                },
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {"code": "INVALID_IMAGE", "message": str(exc), "details": {}},
            },
        ) from exc
    except DetectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "DETECTOR_FAILED",
                    "message": str(exc),
                    "details": {},
                }
            },
        ) from exc


@router.post(
    "/relocate",
    response_model=RelocateResponse,
    summary="重新截图定位当前步骤",
    description="用户按提示完成手动操作后，对新画面检测并更新当前步骤标注。",
)
async def relocate(
    request: RelocateRequest,
    demo_key: str = Depends(verify_demo_key),
):
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
    if request.step_index < 1 or request.step_index > len(state.steps):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_STEP",
                    "message": "step_index 超出范围",
                    "details": {},
                }
            },
        )
    if not request.image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MISSING_IMAGE",
                    "message": "缺少 screenshot image",
                    "details": {},
                }
            },
        )

    step = state.steps[request.step_index - 1]
    try:
        elements, annotation, ref_res, meta = relocate_step_on_screen(
            state.query, step, request.image
        )
    except ValueError as exc:
        if str(exc) == "NO_ELEMENTS_DETECTED":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "NO_ELEMENTS_DETECTED",
                        "message": "新画面中未检测到 UI 元素",
                        "details": {},
                    }
                },
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {"code": "INVALID_IMAGE", "message": str(exc), "details": {}},
            },
        ) from exc
    except DetectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "DETECTOR_FAILED",
                    "message": str(exc),
                    "details": {},
                }
            },
        ) from exc

    step.annotation = annotation
    step.target_element_id = picked.element_id
    step.locate_deferred = False
    step.prepare_hint = None
    state.steps[request.step_index - 1] = step
    state.ui_elements = [e.model_dump() for e in elements]
    task_store.update(state)

    return RelocateResponse(
        success=True,
        step_index=request.step_index,
        target_element_id=step.target_element_id,
        annotation=annotation,
        ui_elements=elements,
        reference_resolution=ref_res,
        detection_meta=meta,
        message="已根据新画面更新标注",
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

    return ReportResponse(received=True)
