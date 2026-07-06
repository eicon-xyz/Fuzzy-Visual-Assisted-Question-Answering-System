"""L4 Locator：单步 Vision 定位，输出 [POINT:x,y:label]。"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from server.models.schemas import Annotation
from server.services.l4.calibration import finalize_l4_annotation
from server.services.l4.config import get_l4_settings
from server.services.l4.llm_client import call_l4_llm
from server.services.l4.pipeline import run_post_pipeline_validate
from server.services.l4.point_parser import build_annotation_from_point, parse_point_tag
from server.services.l4.types import L4LocateResult, L4ScreenContext

logger = logging.getLogger(__name__)

LOCATOR_SYSTEM = """你是 GUI 元素定位器。根据截图与步骤描述，找到应操作的 UI 元素。

你必须在回复的**最后一行**输出恰好一个坐标标签（即使有推理过程也要输出）:
  [POINT:x,y:label]
其中 x,y 为 0–1000 归一化坐标（相对图片宽高，左上角为原点）。
若无法定位，最后一行输出 [POINT:none]。
不要输出其他坐标格式；不要省略 [POINT] 标签。

Windows 桌面快捷方式：查找彩色圆形/方形图标，指向图标中心而非下方文字。
Google Chrome 可能显示为 Google Chrome、Chrome、谷歌浏览器或用户拼写变体（如 GoogleChome）。
桌面图标、回收站等小目标请指向图标中心；小目标也要给出最佳估计坐标，不要轻易输出 [POINT:none]。"""


def _resolve_image_dims(
    image_b64: str,
    screen_ctx: L4ScreenContext,
) -> Tuple[int, int]:
    if screen_ctx.upload_size and len(screen_ctx.upload_size) >= 2:
        return int(screen_ctx.upload_size[0]), int(screen_ctx.upload_size[1])
    try:
        import base64
        from io import BytesIO

        from PIL import Image

        raw = base64.b64decode(image_b64)
        img = Image.open(BytesIO(raw))
        return img.size
    except Exception:
        if screen_ctx.capture_size and len(screen_ctx.capture_size) >= 2:
            return int(screen_ctx.capture_size[0]), int(screen_ctx.capture_size[1])
        return 1280, 720


_DESKTOP_LOCATE_HINT = (
    "请在截图中查找桌面图标区域；小目标也要给出最佳估计坐标，不要轻易 [POINT:none]。"
)

_CHROME_ALIASES = "Google Chrome, Chrome, 谷歌浏览器, GoogleChome, chome"


def locate_l4_step(
    step: dict,
    *,
    image_b64: str,
    screen_ctx: Optional[L4ScreenContext] = None,
    retry_strict: bool = False,
    user_query: str = "",
) -> L4LocateResult:
    cfg = get_l4_settings()
    ctx = screen_ctx or L4ScreenContext()
    step_text = step.get("description") or step.get("target") or str(step)
    action = step.get("action", "click")

    user = (
        f"步骤: {step_text}\n"
        f"动作: {action}\n"
        f"目标元素: {step.get('target', '')}\n"
    )
    if user_query:
        user += f"用户原始任务: {user_query}\n"
    if any(k in step_text.lower() for k in ("chrome", "google", "浏览器")):
        user += f"目标别名: {_CHROME_ALIASES}\n"
    if any(k in step_text for k in ("桌面", "快捷方式", "图标", "icon")):
        user += f"{_DESKTOP_LOCATE_HINT}\n"
    if ctx.screen_hints:
        user += f"\n屏幕上下文:\n{ctx.screen_hints}\n"
    if retry_strict:
        user += "\n上次未返回有效 [POINT]，请仔细查看截图并给出精确坐标。\n"

    raw, meta = call_l4_llm(
        role="locator",
        system=LOCATOR_SYSTEM,
        user=user,
        image_b64=image_b64,
        vision=True,
    )
    meta["raw_locator_output"] = (raw or "")[:500]

    _, coord, label = parse_point_tag(raw)
    ok, err = run_post_pipeline_validate(
        step_text=step_text,
        has_point=coord is not None,
        strict=cfg.strict_locate and not retry_strict,
    )
    if not ok and cfg.strict_locate and not retry_strict:
        logger.warning("L4 locate strict fail, retrying: %s", err)
        return locate_l4_step(
            step,
            image_b64=image_b64,
            screen_ctx=ctx,
            retry_strict=True,
            user_query=user_query,
        )

    if not coord:
        snippet = (raw or "")[:200].replace("\n", " ")
        reason = "point_none" if "[POINT:none" in (raw or "") else "no_point"
        meta["locate_failure_reason"] = reason
        logger.warning(
            "L4 locate failed: %s (step=%r) raw=%r",
            reason,
            step_text[:80],
            snippet,
        )
        return L4LocateResult(llm_meta=meta, confidence=0.0)

    up_w, up_h = _resolve_image_dims(image_b64, ctx)
    ann = build_annotation_from_point(
        coord["x"],
        coord["y"],
        up_w,
        up_h,
        label=label or step.get("target") or "点击此处",
    )
    ann, ref = finalize_l4_annotation(ann, ctx, up_w, up_h)
    meta["coord_normalized"] = coord
    return L4LocateResult(
        annotation=ann,
        reference_resolution=ref,
        llm_meta=meta,
        confidence=0.85 if retry_strict else 0.9,
    )
