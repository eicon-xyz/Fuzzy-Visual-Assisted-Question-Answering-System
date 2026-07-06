"""L4 编排：process + locate，供 router / demo 调用。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from server.models.schemas import Annotation
from server.services.l4.config import get_l4_settings
from server.services.l4.locator import locate_l4_step
from server.services.l4.pipeline import run_pre_pipeline
from server.services.l4.planner import plan_l4_steps
from server.services.l4.step_utils import apply_step_interaction, step_needs_locate
from server.services.l4.types import L4ProcessResult, L4ScreenContext

logger = logging.getLogger(__name__)


def _normalize_l4_steps(steps: List[dict]) -> List[dict]:
    out: List[dict] = []
    for raw in steps:
        step = apply_step_interaction(dict(raw))
        step.setdefault("target_element_id", "")
        step.setdefault("description", step.get("target") or step.get("action") or "")
        step.setdefault("action", step.get("action") or "操作")
        out.append(step)
    return out


def _find_first_locatable_step(steps: List[dict]) -> Optional[int]:
    """process 预定位仅第 1 步（index 0）且需屏幕定位时执行。"""
    if steps and step_needs_locate(steps[0]):
        return 0
    return None


def _build_screen_ctx(
    capture_size: Optional[List[int]] = None,
    upload_size: Optional[List[int]] = None,
    screen_metrics: Optional[dict] = None,
    window_title: Optional[str] = None,
) -> L4ScreenContext:
    ctx = L4ScreenContext(
        capture_size=capture_size,
        upload_size=upload_size,
        screen_metrics=screen_metrics,
        window_title=window_title,
    )
    cfg = get_l4_settings()
    return run_pre_pipeline(ctx, enabled=cfg.pipeline_enabled)


def run_l4_process(
    user_query: str,
    *,
    image_b64: Optional[str] = None,
    capture_size: Optional[List[int]] = None,
    upload_size: Optional[List[int]] = None,
    screen_metrics: Optional[dict] = None,
    window_title: Optional[str] = None,
    assist_bundle: Optional[dict] = None,
    constraints: Optional[dict] = None,
    locate_first_step: bool = True,
) -> L4ProcessResult:
    ctx = _build_screen_ctx(
        capture_size=capture_size,
        upload_size=upload_size,
        screen_metrics=screen_metrics,
        window_title=window_title,
    )

    steps, plan_meta = plan_l4_steps(
        user_query,
        image_b64=image_b64,
        screen_ctx=ctx,
        constraints=constraints,
    )
    steps = _normalize_l4_steps(steps)

    first_ann: Optional[Annotation] = None
    ref_res = ctx.reference_resolution
    locate_meta: Dict[str, Any] = {}

    if locate_first_step and steps and image_b64:
        idx = _find_first_locatable_step(steps)
        if idx == 0:
            from server.services.assist.adapters.l4 import locate_step_with_assist

            first_ann, ref_res_step, locate_meta = locate_step_with_assist(
                steps[idx],
                image_b64=image_b64,
                user_query=user_query,
                assist_bundle=assist_bundle,
                capture_size=capture_size,
                upload_size=upload_size,
                screen_metrics=screen_metrics,
                window_title=window_title,
            )
            ref_res = ref_res_step or ref_res
            locate_meta["located_step_index"] = idx
        else:
            logger.info("L4 process: no locatable step at index 0, skip first locate")

    llm_meta = {
        "route": "L4",
        "planner": plan_meta,
        "locator_first": locate_meta,
    }

    return L4ProcessResult(
        raw_steps=steps,
        constraints=constraints,
        llm_meta=llm_meta,
        reference_resolution=ref_res,
        first_step_annotation=first_ann,
    )


def run_l4_locate_step(
    step: dict,
    *,
    image_b64: str,
    capture_size: Optional[List[int]] = None,
    upload_size: Optional[List[int]] = None,
    screen_metrics: Optional[dict] = None,
    window_title: Optional[str] = None,
    user_query: str = "",
) -> tuple[Optional[Annotation], Optional[List[int]], Dict[str, Any]]:
    if not step_needs_locate(step):
        return None, None, {"skipped": True, "reason": "step_does_not_need_locate"}

    ctx = _build_screen_ctx(
        capture_size=capture_size,
        upload_size=upload_size,
        screen_metrics=screen_metrics,
        window_title=window_title,
    )
    result = locate_l4_step(
        step, image_b64=image_b64, screen_ctx=ctx, user_query=user_query
    )
    return result.annotation, result.reference_resolution, result.llm_meta
