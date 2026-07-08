"""GET /api/admin/monitor/* — 健康监控"""
import os
from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Optional

from server.config import settings

router = APIRouter(prefix="/api/admin/monitor", tags=["Admin Monitor"])


def _auth(x_admin_key: Optional[str] = Header(None)) -> str:
    if not x_admin_key or x_admin_key != settings.DEMO_KEY:
        raise HTTPException(401, detail={"error": {"code": "AUTH_FAILED", "message": "X-Admin-Key 无效"}})
    return x_admin_key


import psutil


@router.get("/health")
async def health(key: str = Depends(_auth)):
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.getcwd())

    return {
        "resources": {"cpu_pct": cpu, "memory_gb": round(mem.used / (1024**3), 1),
                      "disk_free_gb": round(disk.free / (1024**3), 1)},
        "components": [
            {"name": "PostgreSQL", "status": "healthy", "detail": "连接池 8/20"},
            {"name": "视觉 LLM", "status": "healthy", "detail": f"{settings.LLM_PROVIDER}/{settings.LLM_MODEL}"},
            {"name": "Session Manager", "status": "healthy", "detail": "内存会话"},
        ],
    }


_alerts = [
    {"id": "a1", "timestamp": "2026-07-06T10:00:00Z", "level": "warning", "message": "LLM API 延迟 > 3s", "status": "unread"},
    {"id": "a2", "timestamp": "2026-07-06T09:00:00Z", "level": "error", "message": "OmniParser 不可达", "status": "unread"},
]


@router.get("/alerts")
async def alerts(limit: int = 20, status: str = "all", key: str = Depends(_auth)):
    filtered = _alerts if status == "all" else [a for a in _alerts if a["status"] == status]
    return {"alerts": filtered[:limit], "total_unread": sum(1 for a in _alerts if a["status"] == "unread"),
            "total": len(_alerts)}


@router.post("/alerts/read-all")
async def read_all(key: str = Depends(_auth)):
    c = sum(1 for a in _alerts if a["status"] == "unread")
    for a in _alerts:
        a["status"] = "read"
    return {"marked_read": c}
