"""
HAJIMI Audit API 路由
======================
C 端审计代理 HTTP 上报接口。
对应 a-c-api-contract.md §3.1 的 /api/audit/* 端点。
"""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

from server.config import settings
from server.database import SessionLocal
from server.database.models import Transaction, Feedback

router = APIRouter(prefix="/api/audit", tags=["Audit"])


# ── 认证 ──

def verify_demo_key(x_demo_key: Optional[str] = Header(None)) -> str:
    if not x_demo_key or x_demo_key != settings.DEMO_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "AUTH_FAILED", "message": "X-Demo-Key 无效", "details": {}}},
        )
    return x_demo_key


# ── 请求模型 ──

class AuditRecord(BaseModel):
    task_id: str
    query: str
    intent_category: str
    complexity_score: int = 0
    route: str = "L2"
    total_steps: int = 1
    completed_steps: int = 1
    result: str = "success"
    duration_ms: int = 0
    feedback_type: Optional[str] = None
    fingerprint_mismatches: int = 0
    redline_triggered: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class AuditBatchRequest(BaseModel):
    client_id: str
    batch: List[AuditRecord]


class FeedbackRequest(BaseModel):
    task_id: str
    feedback_type: str = Field(..., pattern="^(useful|useless|neutral)$")
    comment: Optional[str] = None


# ── 路由 ──

@router.post("/report", summary="批量审计上报")
async def audit_report(
    request: AuditBatchRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """C 端审计代理批量上报脱敏后的审计日志"""
    db = SessionLocal()
    saved = 0
    try:
        for rec in request.batch:
            try:
                tx = Transaction(
                    task_id=rec.task_id,
                    user_query=rec.query,
                    intent_summary=rec.query[:50],
                    intent_category=rec.intent_category,
                    plan_type=rec.route,  # L2 or L3
                    complexity_score=rec.complexity_score,
                    result=rec.result,
                    duration_ms=rec.duration_ms,
                    redline_triggered=rec.redline_triggered,
                    timestamp=datetime.fromisoformat(rec.timestamp.replace("Z", "+00:00"))
                        if rec.timestamp else datetime.now(),
                )
                db.add(tx)
                saved += 1
            except Exception:
                continue
        db.commit()
    finally:
        db.close()

    return {
        "received": saved,
        "server_queue_depth": 0,
    }


@router.post("/feedback", summary="用户反馈上报")
async def audit_feedback(
    request: FeedbackRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """C 端审计代理上报用户反馈"""
    from sqlalchemy.exc import IntegrityError
    db = SessionLocal()
    try:
        fb = Feedback(
            task_id=request.task_id,
            user_id=None,
            feedback_type=request.feedback_type,
            comment=request.comment or "",
        )
        db.add(fb)
        db.commit()
    except IntegrityError:
        db.rollback()
        # FOREIGN KEY 约束：task_id 不存在时仍返回成功
        pass
    finally:
        db.close()
    return {"received": True}
