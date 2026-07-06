"""L4 Adapter — 唯一触碰 L4 定位的薄层。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from server.models.schemas import Annotation
from server.services.assist import build_assist_context, try_hybrid_locate
from server.services.assist.config import ASSIST_ENABLED
from server.services.assist.roi import crop_image_to_foreground_roi
from server.services.l4.orchestrator import run_l4_locate_step
from server.services.l4.types import L4ScreenContext
from server.services.l4.pipeline import build_screen_hints


def _merge_screen_hints(ctx_hints: str, l4_ctx: L4ScreenContext) -> L4ScreenContext:
    base = l4_ctx.screen_hints or build_screen_hints(l4_ctx)
    if ctx_hints:
        l4_ctx.screen_hints = f"{base}\n{ctx_hints}".strip()
    else:
        l4_ctx.screen_hints = base
    return l4_ctx


def locate_step_with_assist(
    step: dict,
    *,
    image_b64: str,
    user_query: str = "",
    assist_bundle: Optional[dict] = None,
    capture_size: Optional[List[int]] = None,
    upload_size: Optional[List[int]] = None,
    screen_metrics: Optional[dict] = None,
    window_title: Optional[str] = None,
) -> Tuple[Optional[Annotation], Optional[List[int]], Dict[str, Any]]:
    """Hybrid 优先；未命中回落 L4 Vision locate。"""
    assist_ctx = build_assist_context(
        assist_bundle,
        capture_size=capture_size,
        upload_size=upload_size,
        screen_metrics=screen_metrics,
    )

    if ASSIST_ENABLED:
        hybrid = try_hybrid_locate(
            step,
            image_b64=image_b64,
            user_query=user_query,
            ctx=assist_ctx,
        )
        if hybrid.hit:
            meta = dict(hybrid.meta)
            meta["assist_hit"] = True
            meta["route"] = "assist_hybrid"
            return hybrid.annotation, hybrid.reference_resolution, meta

    vision_b64 = image_b64
    roi_meta: Dict[str, Any] = {}
    if ASSIST_ENABLED and assist_ctx.foreground.get("rect"):
        vision_b64, offset, cropped = crop_image_to_foreground_roi(
            image_b64,
            assist_ctx.foreground.get("rect"),
            capture_size,
        )
        if cropped:
            roi_meta["roi_cropped"] = True
            roi_meta["roi_offset"] = offset

    ann, ref, meta = run_l4_locate_step(
        step,
        image_b64=vision_b64,
        capture_size=capture_size,
        upload_size=upload_size,
        screen_metrics=screen_metrics,
        window_title=window_title or (assist_ctx.foreground.get("window_title") or ""),
        user_query=user_query,
    )
    if roi_meta:
        meta = {**meta, **roi_meta}
    if ASSIST_ENABLED:
        meta["assist_hit"] = False
        if assist_ctx.prompt_hints:
            meta["assist_hints"] = assist_ctx.prompt_hints
    return ann, ref, meta
