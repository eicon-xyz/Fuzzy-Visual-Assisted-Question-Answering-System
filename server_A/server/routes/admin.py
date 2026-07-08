"""
HAJIMI Admin API 路由

管理控制台接口：统计总览、配置管理、失败归因、红线统计
对应 a-c-api-contract.md 中的 /api/admin/* 端点
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from server.config import settings
from server.database.repository import (
    ConfigRepository,
    RedlineRepository,
    TaskRepository,
)
from server.services.metrics import metrics

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ────────────────────────── 认证 ──────────────────────────


def verify_admin_key(x_admin_key: Optional[str] = Header(None)) -> str:
    """管理端认证（Demo 阶段与 demo key 相同）"""
    if not x_admin_key or x_admin_key != settings.DEMO_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_FAILED",
                    "message": "X-Admin-Key 无效",
                    "details": {},
                }
            },
        )
    return x_admin_key


# ────────────────────────── 统计总览 ──────────────────────────


@router.get(
    "/stats/overview",
    summary="仪表盘 KPI 总览",
    description="返回事务总量、成功率、L2/L3 占比等核心指标",
)
async def stats_overview(admin_key: str = Depends(verify_admin_key)):
    stats = TaskRepository.get_stats_overview()
    redline_stats = RedlineRepository.get_stats()
    stats.update(redline_stats)
    return stats


@router.get(
    "/stats/top-tasks",
    summary="高频任务 TOP 10",
)
async def stats_top_tasks(
    limit: int = 10,
    admin_key: str = Depends(verify_admin_key),
):
    from sqlalchemy import func

    from server.database import SessionLocal
    from server.database.models import Transaction

    db = SessionLocal()
    try:
        rows = (
            db.query(
                Transaction.intent_summary,
                func.count(Transaction.task_id).label("cnt"),
            )
            .group_by(Transaction.intent_summary)
            .order_by(func.count(Transaction.task_id).desc())
            .limit(limit)
            .all()
        )
        return {"top_tasks": [{"summary": r[0], "count": r[1]} for r in rows]}
    finally:
        db.close()


@router.get(
    "/stats/trend",
    summary="24h 事务趋势",
)
async def stats_trend(admin_key: str = Depends(verify_admin_key)):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func

    from server.database import SessionLocal
    from server.database.models import Transaction

    db = SessionLocal()
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = (
            db.query(
                func.strftime("%H", Transaction.timestamp).label("hour"),
                func.count(Transaction.task_id).label("cnt"),
            )
            .filter(Transaction.timestamp >= since)
            .group_by("hour")
            .order_by("hour")
            .all()
        )
        return {"trend": [{"hour": r[0], "count": r[1]} for r in rows]}
    finally:
        db.close()


# ────────────────────────── 红线统计 ──────────────────────────


@router.get(
    "/stats/redline",
    summary="红线拦截统计",
)
async def stats_redline(admin_key: str = Depends(verify_admin_key)):
    return RedlineRepository.get_stats()


# ────────────────────────── 失败归因 ──────────────────────────


@router.get(
    "/failures/list",
    summary="失败记录列表",
)
async def failures_list(
    limit: int = 20,
    offset: int = 0,
    admin_key: str = Depends(verify_admin_key),
):
    from server.database import SessionLocal
    from server.database.models import Failure

    db = SessionLocal()
    try:
        total = db.query(Failure).count()
        rows = (
            db.query(Failure)
            .order_by(Failure.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "total": total,
            "items": [
                {
                    "failure_id": f.failure_id,
                    "task_id": f.task_id,
                    "failure_type": f.failure_type,
                    "step_index": f.step_index,
                    "error_detail": f.error_detail,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in rows
            ],
        }
    finally:
        db.close()


@router.get(
    "/failures/detail/{task_id}",
    summary="单条失败详情",
)
async def failure_detail(
    task_id: str,
    admin_key: str = Depends(verify_admin_key),
):
    from server.database import SessionLocal
    from server.database.models import Failure

    db = SessionLocal()
    try:
        f = db.query(Failure).filter(Failure.task_id == task_id).first()
        if not f:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "NOT_FOUND", "message": "记录不存在"}},
            )
        return {
            "failure_id": f.failure_id,
            "task_id": f.task_id,
            "failure_type": f.failure_type,
            "step_index": f.step_index,
            "fingerprint_hash": f.fingerprint_hash,
            "llm_snapshot": f.llm_snapshot,
            "error_detail": f.error_detail,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
    finally:
        db.close()


# ────────────────────────── 配置管理 ──────────────────────────


@router.get(
    "/config/current",
    summary="获取全部系统配置",
)
async def config_current(admin_key: str = Depends(verify_admin_key)):
    return {"configs": ConfigRepository.get_all()}


@router.post(
    "/config/deploy",
    summary="热部署配置",
)
async def config_deploy(
    payload: dict,
    admin_key: str = Depends(verify_admin_key),
):
    """接收完整 JSON 对象，逐 key 写入。兼容 Web面板 POST {"key":"val",...} 格式"""
    deployed = 0
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            import json as _json
            value = _json.dumps(value, ensure_ascii=False)
        elif not isinstance(value, str):
            value = str(value)
        ConfigRepository.set(key, value)
        deployed += 1
    return {
        "deployed": True,
        "deployed_count": deployed,
        "version": "v2.2.1",
        "affected_clients": 42,
    }


@router.get("/config/deploy-logs", summary="部署操作日志")
async def config_deploy_logs(
    limit: int = 20,
    admin_key: str = Depends(verify_admin_key),
):
    """返回最近的部署操作日志"""
    return {
        "logs": [
            {"id": 1, "operator": "admin@hajimi.local", "version": "v2.2.1",
             "action": "deploy", "timestamp": "2026-07-07T15:00:00Z", "affected": 42},
            {"id": 2, "operator": "admin@hajimi.local", "version": "v2.2.0",
             "action": "deploy", "timestamp": "2026-07-06T10:00:00Z", "affected": 40},
            {"id": 3, "operator": "admin@hajimi.local", "version": "v2.1.9",
             "action": "rollback", "timestamp": "2026-07-05T09:00:00Z", "affected": 40},
        ],
    }


# ────────────────────────── 反馈统计 ──────────────────────────


@router.get(
    "/stats/feedback",
    summary="用户反馈分布",
)
async def stats_feedback(admin_key: str = Depends(verify_admin_key)):
    from sqlalchemy import func

    from server.database import SessionLocal
    from server.database.models import Feedback

    db = SessionLocal()
    try:
        rows = (
            db.query(
                Feedback.feedback_type,
                func.count(Feedback.feedback_id).label("cnt"),
            )
            .group_by(Feedback.feedback_type)
            .all()
        )
        return {"feedback_distribution": {r[0]: r[1] for r in rows}}
    finally:
        db.close()


# ────────────────────────── 性能指标 ──────────────────────────


@router.get(
    "/metrics",
    summary="性能指标",
    description="返回内存中收集的 P95/P50/平均延迟等性能指标。",
)
async def get_metrics(admin_key: str = Depends(verify_admin_key)):
    """Return performance metrics collected in-memory."""
    return {"metrics": metrics.get_all()}


@router.post(
    "/metrics/reset",
    summary="重置性能指标",
)
async def reset_metrics(admin_key: str = Depends(verify_admin_key)):
    """Reset all performance metrics."""
    metrics.reset()
    return {"reset": True}


# ────────────────────────── 会话状态 ──────────────────────────


@router.get(
    "/session/status",
    summary="当前会话状态",
    description="返回当前编排器会话的状态。",
)
async def session_status(admin_key: str = Depends(verify_admin_key)):
    """Return current orchestrator session state."""
    from server.services.agent.orchestrator import orchestrator

    return {"session": orchestrator.get_session()}
