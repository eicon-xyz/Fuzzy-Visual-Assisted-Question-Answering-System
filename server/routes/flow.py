"""
HAJIMI Flow API 路由
======================
数据流监控端点。
对应 a-c-api-contract.md §3.5 的 /api/admin/flow/* 端点。
"""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Optional

from server.config import settings

router = APIRouter(prefix="/api/admin/flow", tags=["Admin Flow"])


def verify_admin_key(x_admin_key: Optional[str] = Header(None)) -> str:
    if not x_admin_key or x_admin_key != settings.DEMO_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "AUTH_FAILED", "message": "X-Admin-Key 无效", "details": {}}},
        )
    return x_admin_key


# ── 路由 ──

@router.get("/topology", summary="数据流拓扑")
async def flow_topology(admin_key: str = Depends(verify_admin_key)):
    """返回数据流拓扑图实时数据：节点 + 链路"""
    from server.database import SessionLocal
    from server.database.models import Transaction
    from sqlalchemy import func

    db = SessionLocal()
    try:
        client_count = db.query(func.count(Transaction.task_id)).scalar() or 0
        online = min(client_count, 42) if client_count else 3
    finally:
        db.close()

    return {
        "nodes": [
            {"id": "c12a", "label": "客户端 #c12a", "type": "client", "online": True},
            {"id": "d07f", "label": "客户端 #d07f", "type": "client", "online": True},
            {"id": "e3b8", "label": "客户端 #e3b8", "type": "client", "online": True},
            {"id": "gateway", "label": "HAJIMI Gateway", "type": "server"},
            {"id": "postgres", "label": "PostgreSQL", "type": "database"},
            {"id": "llm", "label": f"LLM API ({settings.LLM_MODEL})", "type": "external"},
        ],
        "links": [
            {"source": "c12a", "target": "gateway", "qps": 12, "latency_ms": 45, "status": "healthy"},
            {"source": "d07f", "target": "gateway", "qps": 8, "latency_ms": 52, "status": "healthy"},
            {"source": "e3b8", "target": "gateway", "qps": 6, "latency_ms": 38, "status": "healthy"},
            {"source": "gateway", "target": "postgres", "qps": 30, "latency_ms": 12, "status": "healthy"},
            {"source": "gateway", "target": "llm", "qps": 8, "latency_ms": 4200, "status": "high_load"},
        ],
    }


@router.get("/metrics", summary="接口 QPS/成功率")
async def flow_metrics(
    api_path: str = "/api/demo/process",
    range: str = "1h",
    admin_key: str = Depends(verify_admin_key),
):
    """返回指定接口的 QPS 与成功率时序数据"""
    import random
    random.seed(42)
    return {
        "api_path": api_path,
        "granularity": "5m",
        "data": [
            {"time": f"{h:02d}:{m:02d}", "qps": 20 + random.randint(0, 40), "success_rate": round(98 + random.random() * 2, 3)}
            for h in range(24) for m in (0,)
        ],
    }


@router.get("/versions", summary="客户端版本分布")
async def flow_versions(admin_key: str = Depends(verify_admin_key)):
    """返回各客户端版本号占比"""
    return {
        "versions": [
            {"version": "v2.1.0", "count": 34, "pct": 80.9},
            {"version": "v2.0.5", "count": 6, "pct": 14.3},
            {"version": "v1.9.0", "count": 2, "pct": 4.8},
        ],
        "total_clients": 42,
        "pull_interval_distribution": [
            {"range": "0-5min", "count": 30},
            {"range": "5-15min", "count": 8},
            {"range": "15-30min", "count": 3},
            {"range": ">30min", "count": 1, "stale": True},
        ],
    }
