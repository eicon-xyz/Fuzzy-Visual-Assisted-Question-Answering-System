"""C 端配置拉取 — GET /api/config/pull (ETag)"""
import hashlib, json
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse
from typing import Optional

from server.config import settings
from server.database import SessionLocal
from server.database.models import SystemConfig

router = APIRouter(prefix="/api/config", tags=["Config Client"])


def _auth(x_demo_key: Optional[str] = Header(None)) -> str:
    if not x_demo_key or x_demo_key != settings.DEMO_KEY:
        raise HTTPException(401, detail={"error": {"code": "AUTH_FAILED", "message": "X-Demo-Key 无效"}})
    return x_demo_key


@router.get("/pull")
async def pull(req: Request, key: str = Depends(_auth)):
    db = SessionLocal()
    try:
        rows = db.query(SystemConfig).all()
        config_dict = {r.config_key: r.config_value for r in rows}
        if not config_dict:
            config_dict = {
                "version": "v2.0", "llm_provider": settings.LLM_PROVIDER,
                "llm_model": settings.LLM_MODEL, "llm_temperature": 0.3,
                "llm_max_tokens": 4096, "confidence_threshold": 80,
                "max_blueprint_steps": 15, "config_pull_interval_min": 30,
                "audit_batch_size": 10, "offline_tts_engine": "pyttsx3",
                "routing_rules": {"length_weight": 0.3, "verb_weight": 8, "cross_app_bonus": 10, "threshold_score": 30},
                "updated_at": "2026-07-06T00:00:00Z",
            }

        etag = '"' + hashlib.md5(json.dumps(config_dict, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12] + '"'
        if_none = req.headers.get("If-None-Match", "")
        if if_none and if_none == etag:
            return JSONResponse(status_code=304, content=None)

        return JSONResponse(content={"has_update": True, "config": config_dict}, headers={"ETag": etag})
    finally:
        db.close()
