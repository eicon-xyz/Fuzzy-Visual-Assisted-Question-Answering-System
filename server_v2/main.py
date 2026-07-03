"""
HAJIMI Demo Server 入口 — v2.0 with OpenGuider-style orchestrator.

Key changes:
- Initializes SessionManager, InteractionPipeline, TaskOrchestrator at startup
- Wires orchestrator into demo routes for PEER loop guidance
- Falls back to legacy OmniParser pipeline if orchestrator init fails
- Backward compatible: all 7 demo + 9 admin endpoints preserved
"""

import sys
import logging
from pathlib import Path

# Support running from server_v2/ directly: add project root to sys.path
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from server_v2.config import settings
from server_v2.routes.demo import router as demo_router, init_demo_routes
from server_v2.routes.admin import router as admin_router
from server_v2.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("main")

# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="HAJIMI Demo Server v2",
    description="智能桌面指引助手后端 (OpenGuider架构重构版)",
    version="2.0.0",
)

# ── Startup ──────────────────────────────────────────────────────────────────


@app.on_event("startup")
def on_startup():
    """Initialize database + orchestrator + perception subsystems."""
    # 1. Database tables
    init_db()
    logger.info("Database initialized")

    # 2. Try to initialize orchestrator (non-fatal — falls back to legacy)
    try:
        _init_orchestrator()
        logger.info("TaskOrchestrator initialized (OpenGuider PEER loop)")
    except Exception as e:
        logger.warning(f"Orchestrator init failed, using legacy fallback: {e}")


def _init_orchestrator():
    """Initialize the full orchestrator stack."""
    from session.session_manager import SessionManager
    from agent.interaction_pipeline import InteractionPipeline
    from agent.task_orchestrator import TaskOrchestrator

    # Create session manager
    session_manager = SessionManager()

    # Create interaction pipeline
    interaction_pipeline = InteractionPipeline(enabled=True)

    # Create orchestrator
    orchestrator = TaskOrchestrator(
        session_manager=session_manager,
        interaction_pipeline=interaction_pipeline,
        capture_screen_fn=None,  # Use default (stub — frontend provides screenshots)
    )

    # Wire into demo routes
    init_demo_routes(orchestrator, settings)

    # Pre-warm perception modules (non-blocking)
    try:
        from perception.ocr_engine import get_ocr_engine
        engine = get_ocr_engine()
        if engine.available:
            logger.info("Tesseract OCR engine ready")
        else:
            logger.warning("Tesseract OCR not available — text detection disabled")
    except Exception as e:
        logger.warning(f"OCR pre-warm failed: {e}")

    try:
        from perception.ui_scanner import _get_implementation
        impl = _get_implementation()
        if impl:
            logger.info(f"UI Automation backend: {impl}")
        else:
            logger.warning("UI Automation not available — element scanning disabled")
    except Exception as e:
        logger.warning(f"UIA probe failed: {e}")

    try:
        from perception.window_enum import enumerate_active_app
        winfo = enumerate_active_app()
        if winfo and winfo.focused_window:
            logger.info(f"Window enumeration ready (focused: '{winfo.focused_window.title}')")
        else:
            logger.warning("Window enumeration available but no windows detected")
    except Exception as e:
        logger.warning(f"Window enumeration probe failed: {e}")


# ── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
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


# ── Routes ───────────────────────────────────────────────────────────────────

app.include_router(demo_router)
app.include_router(admin_router)


@app.get("/")
async def root():
    return {
        "name": "HAJIMI Demo Server v2",
        "version": "2.0.0",
        "architecture": "OpenGuider-style PEER loop",
        "docs": "/docs",
    }


@app.get("/v2/perception/status")
async def perception_status():
    """Report local perception subsystem status."""
    status = {"ocr": False, "uia": False, "uia_impl": None, "windows": False}

    try:
        from perception.ocr_engine import get_ocr_engine
        status["ocr"] = get_ocr_engine().available
    except Exception as e:
        status["ocr_error"] = str(e)

    try:
        from perception.ui_scanner import _get_implementation, query_ui_automation
        impl = _get_implementation()
        status["uia_impl"] = impl
        elements = query_ui_automation(max_elements=10)
        status["uia"] = len(elements) > 0
        status["uia_sample_count"] = len(elements)
    except Exception as e:
        status["uia_error"] = str(e)

    try:
        from perception.window_enum import enumerate_active_app
        winfo = enumerate_active_app()
        status["windows"] = winfo is not None
        if winfo and winfo.focused_window:
            status["focused_window"] = winfo.focused_window.title[:60]
        status["visible_windows"] = len([w for w in (winfo.windows or []) if not w.minimized])
    except Exception as e:
        status["window_error"] = str(e)

    return status


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
