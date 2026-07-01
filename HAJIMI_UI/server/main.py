"""
HAJIMI Demo Server 入口
"""
import sys
from pathlib import Path

# 支持从 server/ 目录直接运行：把项目根目录加入 sys.path
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from server.config import settings
from server.routes.demo import router as demo_router


app = FastAPI(
    title="HAJIMI Demo Server",
    description="智能桌面指引助手 Demo 后端服务",
    version="1.0.0",
)

# ────────────────────────── 中间件 ──────────────────────────

# CORS 全放通，方便 PyQt5 / Vue 前端调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 统一异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(exc),
                "details": {},
            }
        },
    )


# ────────────────────────── 路由注册 ──────────────────────────

app.include_router(demo_router)


@app.get("/")
async def root():
    return {
        "name": "HAJIMI Demo Server",
        "version": "1.0.0",
        "docs": "/docs",
    }


# ────────────────────────── 启动入口 ──────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "server.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
