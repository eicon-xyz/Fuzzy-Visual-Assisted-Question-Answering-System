"""
C 端审计代理 HTTP 上报 — POST /api/audit/report + /api/audit/feedback
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from typing import Optional, List

from server.config import settings
from server.database import SessionLocal
from server.database.models import Transaction, Feedback

router = APIRouter(prefix="/api/audit", tags=["Audit"])


def _auth(x_demo_key: Optional[str] = Header(None)) -> str:
    if not x_demo_key or x_demo_key != settings.DEMO_KEY:
        raise HTTPException(401, detail={"error": {"code": "AUTH_FAILED", "message": "X-Demo-Key 无效"}})
    return x_demo_key


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
    timestamp: Optional[str] = None

class AuditBatch(BaseModel):
    client_id: str
    batch: List[AuditRecord]

class FeedbackReq(BaseModel):
    task_id: str
    feedback_type: str = Field(pattern="^(useful|useless|neutral)$")
    comment: Optional[str] = None


@router.post("/report")
async def report(req: AuditBatch, key: str = Depends(_auth)):
    db = SessionLocal()
    saved = 0
    try:
        for r in req.batch:
            existing = db.query(Transaction).filter(Transaction.task_id == r.task_id).first()
            if existing:
                saved += 1; continue
            db.add(Transaction(
                task_id=r.task_id, user_query=r.query, intent_summary=r.query[:50],
                intent_category=r.intent_category, plan_type=r.route,
                complexity_score=r.complexity_score, result=r.result,
                duration_ms=r.duration_ms, redline_triggered=r.redline_triggered,
                timestamp=datetime.fromisoformat(r.timestamp.replace("Z", "+00:00"))
                if r.timestamp else datetime.now(timezone.utc),
            ))
            saved += 1
        db.commit()
    finally:
        db.close()
    return {"received": saved, "server_queue_depth": 0}


@router.post("/feedback")
async def feedback(req: FeedbackReq, key: str = Depends(_auth)):
    db = SessionLocal()
    try:
        db.add(Feedback(task_id=req.task_id, feedback_type=req.feedback_type, comment=req.comment or ""))
        db.commit()
    except IntegrityError:
        db.rollback()
    finally:
        db.close()
    return {"received": True}
