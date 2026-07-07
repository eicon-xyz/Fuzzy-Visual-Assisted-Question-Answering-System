"""
Per-step Vision LLM locator — outputs normalized [POINT:x,y:label] coordinates.
"""
from __future__ import annotations

from typing import Optional, Tuple

from server.models.schemas import Annotation
from server.services.llm.client import _call_provider_once, _get_api_config, _llm_provider_chain, LlmProvider
from server.services.vision.point_parser import (
    build_annotation_from_point,
    parse_point_tag,
)

LOCATOR_SYSTEM = """你是桌面指引助手，帮助用户在当前截图上定位下一步点击目标。
在 explanation 字段中必须嵌入 [POINT:x,y:label] 标签。
坐标规则：x,y 为 0-1000 归一化坐标（左上 0,0，右下 1000,1000），禁止输出像素值。
若目标不可见，shouldPoint 为 false，不要编造坐标。
严格返回 JSON：
{
  "shouldPoint": true,
  "label": "按钮名称",
  "explanation": "说明文字 [POINT:850,450:Submit]"
}"""


def _resolve_image_size(image_base64: str) -> Tuple[int, int]:
    import base64
    import io

    from PIL import Image

    raw = image_base64
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(raw.strip())
        with Image.open(io.BytesIO(data)) as img:
            return img.width, img.height
    except Exception:
        return 1920, 1080


def _call_vision_locate(
    query: str,
    image_base64: str,
    *,
    step_action: str = "",
    step_description: str = "",
) -> Tuple[Optional[dict], dict]:
    """Call primary vision-capable provider for step localization."""
    from server.config import reload_settings, settings

    reload_settings()
    llm_meta: dict = {"llm_called": True, "locate_only": True}
    user_text = (
        f"目标步骤：{step_action or step_description}\n"
        f"详细说明：{step_description}\n"
        f"用户目标上下文：{query}"
    )
    chain = _llm_provider_chain(speed_mode="precision")
    if not chain:
        pk, pu, pm = _get_api_config()
        if not pk:
            return None, {**llm_meta, "llm_error": "LLM_API_KEY not configured"}
        chain = [
            LlmProvider(
                "primary",
                pk,
                pu,
                pm,
                float(settings.LLM_VISION_ATTEMPT_TIMEOUT or 45),
                True,
            )
        ]

    errors = []
    for provider in chain:
        if not provider.vision and len(chain) == 1:
            provider = type(provider)(
                name=provider.name,
                api_key=provider.api_key,
                base_url=provider.base_url,
                model=provider.model,
                timeout=float(settings.LLM_VISION_ATTEMPT_TIMEOUT or 45),
                vision=True,
            )
        parsed, err, latency_ms, _ = _call_provider_once(
            provider,
            prompt=LOCATOR_SYSTEM,
            query=user_text,
            image_base64=image_base64,
            temperature=0.1,
            max_tokens=400,
        )
        llm_meta["llm_latency_ms"] = latency_ms
        llm_meta["llm_provider"] = provider.name
        llm_meta["llm_used_vision"] = True
        if parsed:
            explanation = parsed.get("explanation") or ""
            clean, coord, label = parse_point_tag(explanation)
            if coord:
                parsed["_parsed_coord"] = coord
                parsed["_parsed_label"] = label or parsed.get("label") or "element"
                parsed["explanation"] = clean
            return parsed, llm_meta
        if err:
            errors.append(err)
    llm_meta["llm_error"] = "; ".join(errors) if errors else "vision locate failed"
    return None, llm_meta


def locate_step_target_from_image(
    query: str,
    step_action: str,
    step_description: str,
    image_base64: str,
) -> Tuple[Optional[Annotation], Optional[list], dict, Optional[list]]:
    """
    Locate a single step target via Vision LLM.

    Returns:
        (annotation, reference_resolution [w,h], llm_meta, bbox as list)
    """
    w, h = _resolve_image_size(image_base64)
    result, llm_meta = _call_vision_locate(
        query,
        image_base64,
        step_action=step_action,
        step_description=step_description,
    )
    if not result:
        return None, [w, h], llm_meta, None

    coord = result.get("_parsed_coord")
    if not coord and result.get("shouldPoint") is False:
        return None, [w, h], llm_meta, None

    if not coord:
        content = str(result.get("explanation") or "")
        _, coord, label = parse_point_tag(content)
        if not coord:
            return None, [w, h], llm_meta, None
        result["_parsed_label"] = label

    label = result.get("_parsed_label") or result.get("label") or "点击此处"
    ann = build_annotation_from_point(
        coord["x"],
        coord["y"],
        w,
        h,
        label=label,
    )
    from server.services.vision.point_parser import normalized_point_to_bbox

    bbox = normalized_point_to_bbox(coord["x"], coord["y"], w, h)
    return ann, [w, h], llm_meta, bbox


def locate_step_target(
    query: str,
    step_action: str,
    step_description: str,
    image_base64: str,
) -> Tuple[Optional[Annotation], Optional[list], dict]:
    ann, ref, meta, _ = locate_step_target_from_image(
        query, step_action, step_description, image_base64
    )
    return ann, ref, meta
