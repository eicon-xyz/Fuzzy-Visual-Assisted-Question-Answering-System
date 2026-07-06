"""GET /api/admin/flow/* — 数据流监控"""
import random
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from server.config import settings

router = APIRouter(prefix="/api/admin/flow", tags=["Admin Flow"])


def _auth(x_admin_key: Optional[str] = Header(None)) -> str:
    if not x_admin_key or x_admin_key != settings.DEMO_KEY:
        raise HTTPException(
            401,
            detail={"error": {"code": "AUTH_FAILED", "message": "X-Admin-Key 无效"}},
        )
    return x_admin_key


@router.get("/topology")
async def topology(key: str = Depends(_auth)):
    return {
        "nodes": [
            {"id": "c12a", "label": "客户端 #c12a", "type": "client", "online": True},
            {"id": "d07f", "label": "客户端 #d07f", "type": "client", "online": True},
            {"id": "e3b8", "label": "客户端 #e3b8", "type": "client", "online": True},
            {"id": "gateway", "label": "HAJIMI Gateway", "type": "server"},
            {"id": "postgres", "label": "PostgreSQL", "type": "database"},
            {"id": "llm", "label": f"LLM ({settings.LLM_MODEL})", "type": "external"},
        ],
        "links": [
            {"source": "c12a", "target": "gateway", "qps": 12, "latency_ms": 45, "status": "healthy"},
            {"source": "d07f", "target": "gateway", "qps": 8, "latency_ms": 52, "status": "healthy"},
            {"source": "e3b8", "target": "gateway", "qps": 6, "latency_ms": 38, "status": "healthy"},
            {"source": "gateway", "target": "postgres", "qps": 30, "latency_ms": 12, "status": "healthy"},
            {"source": "gateway", "target": "llm", "qps": 8, "latency_ms": 4200, "status": "high_load"},
        ],
    }


@router.get("/metrics")
async def metrics(api_path: str = "/api/demo/process", key: str = Depends(_auth)):
    random.seed(42)
    return {
        "api_path": api_path,
        "granularity": "5m",
        "data": [
            {
                "time": f"{h:02d}:{m:02d}",
                "qps": 20 + random.randint(0, 40),
                "success_rate": round(98 + random.random() * 2, 3),
            }
            for h in range(24)
            for m in (0,)
        ],
    }


@router.get("/versions")
async def versions(key: str = Depends(_auth)):
    return {
        "versions": [
            {"version": "v2.1.0", "count": 34, "pct": 80.9},
            {"version": "v2.0.5", "count": 6, "pct": 14.3},
            {"version": "v1.9.0", "count": 2, "pct": 4.8},
        ],
        "total_clients": 42,
    }
