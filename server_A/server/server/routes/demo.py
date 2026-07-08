"""
HAJIMI 自动操作助手 — Demo API 路由

OmniParser 元素检测 + LLM 执行计划 + SSE 推送 + 自动执行。
"""

import json
import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

from server.config import settings
from server.database.repository import RedlineRepository, TaskRepository
from server.models.schemas import CancelRequest, HealthResponse, ProcessRequest
from server.storage.memory import task_store

router = APIRouter(prefix="/api/demo", tags=["Demo Core"])


# ────────────────────────── 认证 ──────────────────────────


def verify_demo_key(x_demo_key: Optional[str] = Header(None)) -> str:
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


# ────────────────────────── SSE 格式化 ──────────────────────────


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ═══════════════════════════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/health", summary="服务健康检查")
async def health_check():
    """Health check with OmniParser probe."""
    import httpx

    omni_ready = False
    omni_device = None
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{settings.OMNIPARSER_URL}/probe/")
            if resp.status_code == 200:
                data = resp.json()
                omni_ready = data.get("ready", False)
                omni_device = data.get("device", "unknown")
    except Exception:
        pass

    if not omni_ready:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "version": "2.0.0",
                "omniparser_ready": False,
                "omniparser_url": settings.OMNIPARSER_URL,
                "message": "OmniParser 远程服务不可达",
            },
        )

    return HealthResponse(
        status="ok",
        version="2.0.0",
        detector_backend="local_omniparser",
        detector_active="local_omniparser",
        detector_device=omni_device or "cuda",
        omniparser_url=settings.OMNIPARSER_URL,
        omniparser_ready=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 核心流程：规划 + 执行
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/execute", summary="提交执行任务")
async def execute_task(
    request: ProcessRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """
    接收截图与用户指令，生成执行计划并后台通过Agent循环执行。
    """
    from server.services.executor.engine import get_cancel_event
    from server.services.executor.engine import register_task as engine_register
    from server.services.executor.engine import run_plan_agent_loop
    from server.services.executor.safety import check_query
    from server.services.planning.router import process_query as plan_query

    # 0. Redline
    safety = check_query(request.query)
    if safety.level == "red":
        return {
            "success": False,
            "error": {"code": "REDLINE", "message": safety.reason},
        }

    # 1. Planning (text-only, no OmniParser needed for planning)
    try:
        response = plan_query(
            request.query,
            request.image,
            screen_width=getattr(request, "screen_width", 1920),
            screen_height=getattr(request, "screen_height", 1080),
        )
    except Exception as e:
        return {
            "success": False,
            "error": {"code": "PLANNING_FAILED", "message": str(e)},
        }

    if not response.success:
        return {
            "success": False,
            "error": {
                "code": "NO_PLAN",
                "message": getattr(response, "redline", None)
                and response.redline.message
                or "规划失败",
            },
        }

    # 2. Save to stores
    task_store.create(response, request.query)
    TaskRepository.create_from_response(response, request.query)

    # 3. Register task to create the cancel Event (deduplicated — no-op if already exists)
    #    Then get the cancel event for the background thread
    engine_register(
        response.task_id
    )  # idempotent: reuses existing queue if already registered
    cancel_event = get_cancel_event(response.task_id)

    # 4. Convert steps to dicts for engine
    steps_raw = [s.model_dump() for s in response.steps]

    # 5. Background Agent Loop
    thread = threading.Thread(
        target=run_plan_agent_loop,
        args=(response.task_id, response.goal, steps_raw, cancel_event),
        daemon=True,
    )
    thread.start()

    # 6. Return plan immediately
    return {
        "task_id": response.task_id,
        "success": True,
        "plan": {
            "goal": response.goal,
            "total_steps": len(response.steps),
            "steps": [
                {"step_index": s.step_index, "instruction": s.instruction}
                for s in response.steps
            ],
        },
        "screenshot_base64": response.annotated_image,
        "detection_meta": response.detection_meta,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SSE 事件流
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/stream/{task_id}", summary="SSE 执行进度推送")
async def stream_events(task_id: str):
    """实时推送任务执行进度 (Server-Sent Events)。"""
    from server.services.executor.engine import register_task

    # 获取已存在的队列或注册新的
    q = register_task(task_id)

    def generate():
        # 心跳确认连接
        yield _format_sse(
            "heartbeat", {"timestamp": str(time.time()), "task_id": task_id}
        )

        # 持续从队列读取事件
        while True:
            try:
                event = q.get(timeout=30)  # 30s 超时发心跳
                yield _format_sse(event["event"], event["data"])
                if event["event"] in ("task_done", "task_failed", "task_cancelled"):
                    break
            except Exception:
                # 超时发心跳保活
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


# ═══════════════════════════════════════════════════════════════════════════
# 取消任务
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/cancel", summary="取消/停止任务")
async def cancel_task(
    request: CancelRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """
    取消进行中的任务。需要 task_id。
    """
    from server.services.executor.engine import cancel_task as engine_cancel

    ok = engine_cancel(request.task_id)

    # 同时清理 task_store
    state = task_store.get(request.task_id)
    if state:
        from server.services.planning.blueprint_engine import BlueprintEngine

        BlueprintEngine().terminate(state)
        task_store.update(state)

    return {
        "success": ok,
        "message": "任务已取消" if ok else "任务不存在或已结束",
        "task_id": request.task_id,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 兼容旧端点（保留，不破坏现有调用）
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/process", summary="[兼容] 核心流程入口 — 仅规划不执行")
async def process(
    request: ProcessRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """兼容旧版 API：只做规划，不自动执行。"""
    from server.services.planning.router import process_query as plan_query

    response = plan_query(
        request.query,
        request.image,
        screen_width=getattr(request, "screen_width", 1920),
        screen_height=getattr(request, "screen_height", 1080),
    )
    if response.redline and response.redline.triggered:
        RedlineRepository.log(
            query=request.query,
            category=response.redline.category,
            action=response.redline.action,
            message=response.redline.message,
        )
        return response
    task_store.create(response, request.query)
    TaskRepository.create_from_response(response, request.query)
    return response
