"""AssistBundle 摄入与 collector 调度。"""
from __future__ import annotations

from typing import List, Optional

from server.services.assist.collectors.registry import run_collectors
from server.services.assist.config import ASSIST_ENABLED
from server.services.assist.types import AssistContext


def build_assist_context(
    bundle: Optional[dict],
    *,
    capture_size: Optional[List[int]] = None,
    upload_size: Optional[List[int]] = None,
    screen_metrics: Optional[dict] = None,
) -> AssistContext:
    safe_bundle = bundle if isinstance(bundle, dict) else {}
    ctx = AssistContext(
        bundle=safe_bundle,
        capture_size=capture_size,
        upload_size=upload_size,
        screen_metrics=screen_metrics,
    )
    if not ASSIST_ENABLED:
        return ctx
    candidates = run_collectors(ctx)
    ctx.candidates = candidates
    ctx.prompt_hints = _build_prompt_hints(ctx)
    return ctx


def _build_prompt_hints(ctx: AssistContext) -> str:
    parts: List[str] = []
    fg = ctx.foreground
    if fg.get("window_title"):
        parts.append(f"前台窗口: {fg['window_title']}")
    if fg.get("process_name"):
        parts.append(f"进程: {fg['process_name']}")
    if ctx.scene_hint != "unknown":
        parts.append(f"场景: {ctx.scene_hint}")
    if ctx.candidates:
        names = [c.name for c in ctx.candidates[:12] if c.name]
        if names:
            parts.append("结构化候选: " + ", ".join(names))
    return " | ".join(parts)
