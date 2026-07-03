"""
HAJIMI Config Client API 路由
===============================
C 端配置轮询器拉取接口。
对应 a-c-api-contract.md §3.2 的 GET /api/config/pull 端点。
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse
from typing import Optional

from server.config import settings
from server.database import SessionLocal
from server.database.models import SystemConfig

router = APIRouter(prefix="/api/config", tags=["Config Client"])


# ── 认证 ──

def verify_demo_key(x_demo_key: Optional[str] = Header(None)) -> str:
    if not x_demo_key or x_demo_key != settings.DEMO_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "AUTH_FAILED", "message": "X-Demo-Key 无效", "details": {}}},
        )
    return x_demo_key


# ── 路由 ──

@router.get("/pull", summary="客户端配置拉取")
async def config_pull(
    request: Request,
    demo_key: str = Depends(verify_demo_key),
):
    """C 端配置轮询器定时拉取最新配置，支持 ETag"""
    import hashlib, json
    db = SessionLocal()
    try:
        rows = db.query(SystemConfig).all()
        # Key-value → dict
        config_dict = {}
        for row in rows:
            config_dict[row.config_key] = row.config_value
        if not config_dict:
            config_dict = _default_config()

        # ETag = 内容哈希
        etag = '"' + hashlib.md5(
            json.dumps(config_dict, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:12] + '"'

        if_none = request.headers.get("If-None-Match", "")
        if if_none and if_none == etag:
            return JSONResponse(status_code=304, content=None)

        return JSONResponse(
            status_code=200,
            content={"has_update": True, "config": config_dict},
            headers={"ETag": etag},
        )
    finally:
        db.close()


def _default_config() -> dict:
    """默认配置（数据库为空时返回）"""
    return {
        "version": "v2.2.0",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_api_endpoint": settings.LLM_BASE_URL,
        "llm_model": settings.LLM_MODEL,
        "llm_temperature": settings.LLM_TEMPERATURE,
        "llm_max_tokens": settings.LLM_MAX_TOKENS,
        "confidence_threshold": 80,
        "max_blueprint_steps": 15,
        "config_pull_interval_min": 30,
        "audit_batch_size": 10,
        "offline_tts_engine": "pyttsx3",
        "routing_rules": {
            "length_weight": 0.3,
            "verb_weight": 8,
            "cross_app_bonus": 10,
            "threshold_score": 30,
            "custom_keywords": ["安装", "配置", "设置"],
        },
        "updated_at": "2026-07-03T15:00:00Z",
    }
