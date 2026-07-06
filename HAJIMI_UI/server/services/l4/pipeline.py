"""
L4 轻量 interaction pipeline（Pre/Post LLM，不依赖 OmniParser）。

Pre:  屏幕尺寸 / 窗口标题 / 可选 UIA 摘要 → screen_hints
Post: strict locate 二次校验（可选）
"""
from __future__ import annotations

import logging
import platform
from typing import Any, Dict, Optional

from server.services.l4.types import L4ScreenContext

logger = logging.getLogger(__name__)


def _try_uia_summary() -> str:
    if platform.system() != "Windows":
        return ""
    try:
        import uiautomation as auto  # type: ignore

        fg = auto.GetForegroundControl()
        if not fg:
            return ""
        name = fg.Name or ""
        cls = fg.ClassName or ""
        rect = fg.BoundingRectangle
        if rect:
            return (
                f"前台窗口: {name!r} class={cls!r} "
                f"rect=({rect.left},{rect.top},{rect.right},{rect.bottom})"
            )
        return f"前台窗口: {name!r} class={cls!r}"
    except Exception as exc:
        logger.debug("L4 UIA pre-pipeline skipped: %s", exc)
        return ""


def build_screen_hints(
    ctx: L4ScreenContext,
    *,
    include_uia: bool = True,
) -> str:
    parts: list[str] = []
    if ctx.capture_size and len(ctx.capture_size) >= 2:
        parts.append(f"屏幕分辨率: {ctx.capture_size[0]}x{ctx.capture_size[1]}")
    if ctx.window_title:
        parts.append(f"活动窗口: {ctx.window_title}")
    if ctx.screen_metrics:
        dpi = ctx.screen_metrics.get("dpi") or ctx.screen_metrics.get("scale_factor")
        if dpi:
            parts.append(f"DPI/缩放: {dpi}")
    if include_uia:
        uia = _try_uia_summary()
        if uia:
            parts.append(uia)
    return "\n".join(parts)


def run_pre_pipeline(ctx: L4ScreenContext, *, enabled: bool = True) -> L4ScreenContext:
    if not enabled:
        return ctx
    ctx.screen_hints = build_screen_hints(ctx)
    return ctx


def run_post_pipeline_validate(
    *,
    step_text: str,
    has_point: bool,
    strict: bool,
) -> tuple[bool, Optional[str]]:
    """Post-LLM 校验：strict 模式下无坐标则失败。"""
    if has_point:
        return True, None
    if strict:
        return False, f"L4 strict locate: no [POINT] for step: {step_text[:80]}"
    return True, None
