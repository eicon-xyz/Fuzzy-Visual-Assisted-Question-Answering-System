"""
HAJIMI Demo API 路由
实现 api-contract-demo.md 中定义的全部端点
"""
import asyncio
import json
import threading
import time
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import StreamingResponse

from server.config import CONFIG_SOURCE, reload_settings, settings
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
    LocateRequest,
    LocateResponse,
    InspectRequest,
    InspectResponse,
    HealthResponse,
    ErrorResponse,
    Intent,
    CancelRequest,
)
from server.storage.memory import task_store
from server.services.planning.blueprint_engine import BlueprintEngine
from server.services.llm_ai import process_query, get_clarification_question
from server.services.omniparser_client import parse_screenshot, parse_screenshot_full
from server.services.planning.replanner import replan_steps
from server.services.planning.router import relocate_step, locate_step_with_vision, locate_l4_step
from server.services.planning.route_selector import route_uses_per_step_locate
from server.database.repository import (
    TaskRepository, RedlineRepository, FeedbackRepository, FailureRepository,
)


router = APIRouter(prefix="/api/demo", tags=["Demo Core"])


def _screen_ctx_from_request(request) -> dict:
    return {
        "capture_size": getattr(request, "capture_size", None),
        "upload_size": getattr(request, "upload_size", None),
        "screen_metrics": getattr(request, "screen_metrics", None),
        "assist_bundle": getattr(request, "assist_bundle", None),
    }


def _locate_step_for_route(state, step, image: str, request) -> tuple:
    route = getattr(state, "route_mode", "") or ""
    ctx = _screen_ctx_from_request(request)
    if route == "L4":
        return locate_l4_step(
            step.action,
            step.description,
            image,
            step_target=getattr(step, "target", None),
            user_query=state.query,
            window_title=(ctx.get("assist_bundle") or {}).get("foreground", {}).get("window_title"),
            **ctx,
        )
    return locate_step_with_vision(
        getattr(request, "query", None) or state.query,
        step.action,
        step.description,
        image,
    )[:3]


def _probe_omniparser_sync() -> Tuple[bool, Optional[str], str]:
    """同步探测 OmniParser（在线程池中运行，避免阻塞 event loop）。"""
    reload_settings()
    omniparser_ready = False
    detector_device = None
    omni_url = settings.OMNIPARSER_URL.rstrip("/")
    try:
        import httpx

        with httpx.Client(timeout=3, trust_env=False) as client:
            health = client.get(f"{omni_url}/health")
            if health.status_code == 200:
                body = health.json()
                if isinstance(body, dict):
                    omniparser_ready = bool(
                        body.get("ready", body.get("status") == "ok")
                    )
                    detector_device = body.get("device")
            if not omniparser_ready:
                probe = client.get(f"{omni_url}/probe/", timeout=3)
                if probe.status_code == 200:
                    body = probe.json()
                    if isinstance(body, dict):
                        omniparser_ready = bool(body.get("ready", True))
                        detector_device = body.get("device") or detector_device
    except Exception:
        pass
    return omniparser_ready, detector_device, omni_url


def _llm_capability() -> tuple[bool, bool, str]:
    """Returns (llm_configured, l4_capable, routing_mode)."""
    reload_settings()
    routing_mode = getattr(settings, "ROUTING_MODE", "auto") or "auto"
    api_key = settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY or ""
    base_url = (settings.LLM_BASE_URL or settings.DEEPSEEK_BASE_URL or "").strip()
    llm_configured = bool(api_key and base_url)
    l4_capable = llm_configured
    return llm_configured, l4_capable, routing_mode


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


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ────────────────────────── 路由 ──────────────────────────


@router.get(
    "/health/live",
    summary="A 端存活探测",
    description="不探测 OmniParser，仅确认 A 端 event loop 可用。",
)
async def health_live():
    return {"status": "ok", "version": "1.0.0"}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="服务健康检查",
    description="供前端启动时探测后端是否可用，无需认证。",
)
async def health_check():
    omniparser_ready, detector_device, omni_url = await asyncio.to_thread(
        _probe_omniparser_sync
    )
    llm_configured, l4_capable, routing_mode = await asyncio.to_thread(
        _llm_capability
    )

    return HealthResponse(
        status="ok",
        version="1.0.0",
        detector_backend="local_omniparser",
        detector_active="local_omniparser",
        detector_device=detector_device or "cpu",
        omniparser_url=omni_url,
        omniparser_ready=omniparser_ready,
        config_source=CONFIG_SOURCE,
        routing_mode=routing_mode,
        llm_configured=llm_configured,
        l4_capable=l4_capable,
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
    response = await asyncio.to_thread(
        process_query,
        request.query,
        request.image,
        request.screen_fingerprint,
        capture_size=request.capture_size,
        upload_size=request.upload_size,
        screen_metrics=request.screen_metrics,
        window_title=request.window_title,
        assist_bundle=request.assist_bundle,
    )
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


@router.post("/execute", summary="提交 L5 自动执行任务")
async def execute_task(
    request: ProcessRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """接收用户指令，生成执行计划并后台通过 Agent 循环自动执行。

    DEPRECATED: B 端 L5 已改连 new_JIMI Sidecar (:8011)。本路由仅过渡期保留，勿再扩展。
    """
    from server.services.executor.engine import (
        get_cancel_event,
        register_task as engine_register,
        run_plan_agent_loop,
    )
    from server.services.executor.safety import check_query
    from server.services.planning.execute_planning import plan_for_execute

    safety = check_query(request.query)
    if safety.level == "red":
        return {
            "success": False,
            "error": {"code": "REDLINE", "message": safety.reason},
        }

    try:
        response = await asyncio.to_thread(
            plan_for_execute,
            request.query,
            request.image,
            getattr(request, "screen_width", 1920) or 1920,
            getattr(request, "screen_height", 1080) or 1080,
        )
    except Exception as exc:
        return {
            "success": False,
            "error": {"code": "PLANNING_FAILED", "message": str(exc)},
        }

    if not response.success:
        message = "规划失败"
        if response.redline and response.redline.message:
            message = response.redline.message
        return {
            "success": False,
            "error": {"code": "NO_PLAN", "message": message},
        }

    task_store.create(response, request.query)
    TaskRepository.create_from_response(response, request.query)

    engine_register(response.task_id)
    cancel_event = get_cancel_event(response.task_id)

    steps_raw = [
        {"step_index": s.step_index, "instruction": s.description}
        for s in response.steps
    ]

    thread = threading.Thread(
        target=run_plan_agent_loop,
        args=(response.task_id, response.goal or request.query, steps_raw, cancel_event),
        daemon=True,
    )
    thread.start()

    return {
        "task_id": response.task_id,
        "success": True,
        "plan": {
            "goal": response.goal,
            "total_steps": len(response.steps),
            "steps": [
                {"step_index": s.step_index, "instruction": s.description}
                for s in response.steps
            ],
        },
        "screenshot_base64": response.annotated_image,
        "detection_meta": response.detection_meta,
    }


@router.get("/stream/{task_id}", summary="SSE 执行进度推送")
async def stream_events(task_id: str):
    """实时推送 L5 任务执行进度 (Server-Sent Events)。

    DEPRECATED: B 端 SSE 已改连 :8011 Sidecar。
    """
    from server.services.executor.engine import register_task

    q = register_task(task_id)

    def generate():
        yield _format_sse(
            "heartbeat", {"timestamp": str(time.time()), "task_id": task_id}
        )
        while True:
            try:
                event = q.get(timeout=30)
                yield _format_sse(event["event"], event["data"])
                if event["event"] in ("task_done", "task_failed", "task_cancelled"):
                    break
            except Exception:
                yield _format_sse("heartbeat", {"timestamp": str(time.time())})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/cancel", summary="取消/停止 L5 任务")
async def cancel_task(
    request: CancelRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """DEPRECATED: B 端 cancel 已改连 :8011 Sidecar。"""
    from server.services.executor.engine import cancel_task as engine_cancel

    ok = engine_cancel(request.task_id)

    state = task_store.get(request.task_id)
    if state:
        BlueprintEngine().terminate(state)
        task_store.update(state)

    return {
        "success": ok,
        "message": "任务已取消" if ok else "任务不存在或已结束",
        "task_id": request.task_id,
    }


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
    from server.services.parse_cache import get_cached_parse, put_cached_parse
    from server.services.omniparser_client import _maybe_downscale_b64
    from server.config import reload_settings, settings

    def _run_inspect():
        reload_settings()
        fp = request.screen_fingerprint
        image = request.image
        max_side = getattr(settings, "INSPECT_MAX_SIDE", 960)
        cleaned = image
        if image:
            from server.services.omniparser_client import _clean_base64

            payload = _clean_base64(image)
            if payload:
                scaled, _, _ = _maybe_downscale_b64(payload, max_side)
                if scaled != payload:
                    image = f"data:image/jpeg;base64,{scaled}"
        if fp:
            cached = get_cached_parse(fp)
            if cached and cached.elements:
                return cached, True
        result = parse_screenshot_full(image)
        if fp and result.elements:
            put_cached_parse(fp, result)
        return result, False

    result, cache_hit = await asyncio.to_thread(_run_inspect)
    meta = dict(result.detection_meta or {})
    if cache_hit:
        meta["parse_cache_hit"] = True
        meta["parse_latency_ms"] = 0

    return InspectResponse(
        success=True,
        ui_elements=result.elements,
        annotated_image=result.annotated_image,
        reference_resolution=result.reference_resolution,
        detection_meta=meta,
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

        # === 动态重规划 / L4 逐步 Vision 定位 ===
        route_mode = getattr(state, "route_mode", None) or ""
        use_vision_locate = route_uses_per_step_locate(route_mode)

        if (
            action == "advance"
            and request.image
            and next_step
            and (not next_step.target_element_id or use_vision_locate)
        ):
            if (
                use_vision_locate
                and next_step.interaction != "keyboard"
                and not next_step.locate_deferred
            ):
                ann, ref, meta = await asyncio.to_thread(
                    _locate_step_for_route,
                    state,
                    next_step,
                    request.image,
                    request,
                )
                if ann:
                    next_step.target_element_id = "~vision"
                    next_step.annotation = ann
                    if ref:
                        state.ui_elements = state.ui_elements or []
            elif not use_vision_locate and not next_step.target_element_id:
                new_elements = await asyncio.to_thread(parse_screenshot, request.image)
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
    "/locate",
    response_model=LocateResponse,
    summary="Vision 逐步定位",
    description="L4/L3_DEFERRED 路径：对指定步骤用 Vision LLM 定位，跳过 OmniParser。",
)
async def locate(
    request: LocateRequest,
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
                    "code": "INVALID_STEP_INDEX",
                    "message": f"step_index {request.step_index} 超出范围",
                    "details": {},
                }
            },
        )

    target_step = state.steps[request.step_index - 1]

    ann, ref, meta = await asyncio.to_thread(
        _locate_step_for_route,
        state,
        target_step,
        request.image,
        request,
    )

    if ann:
        target_step.target_element_id = "~vision"
        target_step.annotation = ann
        target_step.status = "active"
        task_store.update(state)

    return LocateResponse(
        success=bool(ann),
        task_id=request.task_id,
        step_index=request.step_index,
        target_element_id="~vision" if ann else None,
        annotation=ann,
        reference_resolution=ref,
        detection_meta=meta,
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
    route_mode = getattr(state, "route_mode", "") or ""

    # 3. 对新截图重定位
    if route_mode == "L4":
        ann, ref, _ = await asyncio.to_thread(
            locate_l4_step,
            target_step.action,
            target_step.description,
            request.image,
            step_target=getattr(target_step, "target", None),
            user_query=state.query,
            capture_size=request.capture_size,
            upload_size=request.upload_size,
            screen_metrics=request.screen_metrics,
            assist_bundle=request.assist_bundle,
            window_title=(request.assist_bundle or {}).get("foreground", {}).get("window_title")
            if request.assist_bundle
            else None,
        )
        target_element_id = "~vision" if ann else None
        elements = []
    else:
        target_element_id, annotation, elements, ref = await asyncio.to_thread(
            relocate_step,
            target_step.action,
            target_step.description,
            request.image,
            query=state.query,
            use_vision=route_uses_per_step_locate(route_mode),
        )
        ann = annotation

    # 4. 更新步骤绑定
    if target_element_id:
        target_step.target_element_id = target_element_id
        target_step.annotation = ann
        target_step.status = "active"

    # 5. 持久化
    task_store.update(state)

    return RelocateResponse(
        success=bool(target_element_id),
        task_id=state.task_id,
        step_index=step_index,
        target_element_id=target_element_id,
        annotation=ann,
        ui_elements=elements,
        reference_resolution=ref,
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
