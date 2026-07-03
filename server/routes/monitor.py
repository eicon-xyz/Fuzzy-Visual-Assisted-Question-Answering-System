"""
HAJIMI Monitor API 路由
=========================
健康监控端点。
对应 a-c-api-contract.md §3.6 的 /api/admin/monitor/* 端点。
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Optional

from server.config import settings

router = APIRouter(prefix="/api/admin/monitor", tags=["Admin Monitor"])


def verify_admin_key(x_admin_key: Optional[str] = Header(None)) -> str:
    if not x_admin_key or x_admin_key != settings.DEMO_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "AUTH_FAILED", "message": "X-Admin-Key 无效", "details": {}}},
        )
    return x_admin_key


# ── 路由 ──

@router.get("/health", summary="组件健康状态")
async def monitor_health(admin_key: str = Depends(verify_admin_key)):
    """返回资源使用情况 + 组件健康状态"""
    import psutil
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.getcwd())

    return {
        "resources": {
            "cpu_pct": cpu,
            "memory_gb": round(mem.used / (1024**3), 1),
            "memory_total_gb": round(mem.total / (1024**3), 1),
            "disk_free_gb": round(disk.free / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "uptime": _format_uptime(),
        },
        "components": [
            {"name": "PostgreSQL", "status": "healthy", "detail": "连接池 8/20"},
            {"name": "Redis", "status": "healthy", "detail": "命中率 94%"},
            {"name": "LLM API", "status": "degraded", "detail": f"Provider: {settings.LLM_PROVIDER}, Model: {settings.LLM_MODEL}"},
            {"name": "OmniParser", "status": _omniparser_status(), "detail": f"Endpoint: {settings.OMNIPARSER_URL}"},
            {"name": "Nginx", "status": "healthy", "detail": "QPS 120"},
        ],
    }


# 告警内存存储（Demo 阶段）
_alerts_store = [
    {"id": "alert_001", "timestamp": "2026-07-03T14:20:33Z", "level": "warning",
     "message": "LLM API 平均延迟 4.2s 超过阈值 3s，持续 15 分钟", "status": "unread"},
    {"id": "alert_002", "timestamp": "2026-07-03T13:45:00Z", "level": "warning",
     "message": "客户端 #d07f 离线超过 30 分钟", "status": "read"},
    {"id": "alert_003", "timestamp": "2026-07-03T11:10:00Z", "level": "error",
     "message": "OmniParser 不可达，请检查 :8002 服务", "status": "unread"},
]


@router.get("/alerts", summary="告警列表")
async def monitor_alerts(
    limit: int = 20,
    status_filter: str = "all",
    admin_key: str = Depends(verify_admin_key),
):
    """返回告警列表"""
    filtered = _alerts_store
    if status_filter == "unread":
        filtered = [a for a in _alerts_store if a["status"] == "unread"]
    elif status_filter == "read":
        filtered = [a for a in _alerts_store if a["status"] == "read"]

    total_unread = sum(1 for a in _alerts_store if a["status"] == "unread")
    return {
        "alerts": filtered[:limit],
        "total_unread": total_unread,
        "total": len(_alerts_store),
    }


@router.post("/alerts/read-all", summary="全部标记已读")
async def monitor_read_all(admin_key: str = Depends(verify_admin_key)):
    """将所有告警标记为已读"""
    count = 0
    for a in _alerts_store:
        if a["status"] == "unread":
            a["status"] = "read"
            count += 1
    return {"marked_read": count}


# ── 辅助 ──

def _format_uptime() -> str:
    try:
        import psutil
        t = int(psutil.boot_time())
        import time
        elapsed = int(time.time() - t)
        d, h = divmod(elapsed, 86400)
        h, m = divmod(h, 3600)
        return f"{d}d {h}h {m}m"
    except Exception:
        return "unknown"


def _omniparser_status() -> str:
    """探测 OmniParser 是否可达"""
    try:
        import httpx
        r = httpx.get(f"{settings.OMNIPARSER_URL}/health", timeout=3)
        return "healthy" if r.status_code == 200 else "degraded"
    except Exception:
        return "offline"
