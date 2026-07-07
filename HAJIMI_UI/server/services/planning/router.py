"""
规划路由层 — L2 / L3 / L3_DEFERRED / L4 / BROWSER 多路径
"""
import time
import uuid
from typing import List, Optional, Tuple

from server.config import settings
from server.models.schemas import (
    UIElement,
    Step,
    Blueprint,
    Intent,
    ProcessResponse,
    Annotation,
    RedlineInfo,
)
from server.services.latency_tracker import LatencyBreakdown, PhaseTimer
from server.services.llm import call_deepseek
from server.services.omniparser_client import parse_screenshot, parse_screenshot_full
from server.services.planning.annotation import build_annotation
from server.services.redline_service import check_redline
from server.services.planning.complexity_router import (
    score_complexity,
    generate_l2_steps,
)
from server.services.planning.route_selector import (
    route_skips_omniparser,
    route_uses_per_step_locate,
    select_route,
)
from server.services.plugins.browser_router import generate_browser_plan
from server.services.vision.planner import plan_without_parse
from server.services.l4.orchestrator import run_l4_process
from server.services.vision.locator import locate_step_target_from_image

# 场景 mock 元素（LLM 不可用时的 fallback）
SCENARIO_ELEMENTS = {
    "wechat": [
        UIElement(
            element_id="~1",
            bbox=[120, 340, 240, 380],
            element_type="icon",
            text="Microsoft Edge",
            confidence=0.95,
            center=[180, 360],
        ),
        UIElement(
            element_id="~2",
            bbox=[860, 620, 1020, 660],
            element_type="button",
            text="下载",
            confidence=0.91,
            center=[940, 640],
        ),
        UIElement(
            element_id="~3",
            bbox=[540, 420, 740, 460],
            element_type="input",
            text="",
            confidence=0.88,
            center=[640, 440],
        ),
    ],
    "screenshot": [
        UIElement(
            element_id="~1",
            bbox=[20, 20, 60, 60],
            element_type="icon",
            text="截图工具",
            confidence=0.94,
            center=[40, 40],
        ),
        UIElement(
            element_id="~2",
            bbox=[300, 300, 500, 400],
            element_type="button",
            text="新建截图",
            confidence=0.92,
            center=[400, 350],
        ),
    ],
    "default": [
        UIElement(
            element_id="~1",
            bbox=[100, 100, 200, 140],
            element_type="button",
            text="开始",
            confidence=0.90,
            center=[150, 120],
        ),
        UIElement(
            element_id="~2",
            bbox=[300, 300, 420, 340],
            element_type="button",
            text="设置",
            confidence=0.88,
            center=[360, 320],
        ),
    ],
}


def _choose_scenario(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["微信", "qq", "软件", "下载", "安装"]):
        return "wechat"
    if any(k in q for k in ["截图", "截屏", "snip"]):
        return "screenshot"
    return "default"


_MOCK_FALLBACKS = {
    "wechat": [
        {"action": "打开浏览器", "description": "找到桌面上的浏览器图标，双击打开。", "target_element_id": "~1"},
        {"action": "访问微信官网", "description": "在地址栏输入 weixin.qq.com 并回车。", "target_element_id": ""},
        {"action": "点击下载按钮", "description": "在官网首页找到「下载」按钮并点击。", "target_element_id": "~2"},
        {"action": "运行安装程序", "description": "下载完成后，双击安装包按提示完成安装。", "target_element_id": ""},
    ],
    "screenshot": [
        {"action": "打开截图工具", "description": "按下 Win + Shift + S 打开系统截图工具。", "target_element_id": "~1"},
        {"action": "选择截图区域", "description": "拖动鼠标选择要截取的区域。", "target_element_id": ""},
        {"action": "保存截图", "description": "截图完成后，点击通知中的预览并保存。", "target_element_id": ""},
    ],
    "default": [
        {"action": "观察当前界面", "description": "仔细查看屏幕上的可点击元素。", "target_element_id": "~1"},
        {"action": "按提示操作", "description": "根据系统指引逐步完成目标。", "target_element_id": ""},
    ],
}


def generate_steps(
    query: str,
    elements: Optional[List[UIElement]] = None,
    annotated_image: Optional[str] = None,
    *,
    parse_degraded: bool = False,
) -> tuple[List[dict], Optional[dict], dict]:
    from server.services.llm.client import _get_api_config

    speed_mode = settings.LLM_SPEED_MODE or "fast"
    _, _, model = _get_api_config()
    llm_meta: dict = {
        "llm_called": False,
        "llm_model": model,
        "llm_provider": None,
        "llm_error": None,
        "llm_latency_ms": None,
        "llm_speed_mode": speed_mode,
        "llm_used_vision": False,
    }

    if settings.USE_REAL_LLM:
        api_key, _, _ = _get_api_config()
        if not api_key:
            llm_meta["llm_error"] = "LLM_API_KEY not configured"
        else:
            llm_meta["llm_called"] = True
            use_vision = speed_mode == "precision" and bool(annotated_image)
            max_tokens = 600 if speed_mode == "fast" else 1200
            llm_response, err, latency, provider, used_vision = call_deepseek(
                query,
                elements=elements,
                image_base64=annotated_image if use_vision else None,
                speed_mode=speed_mode,
                max_tokens=max_tokens,
            )
            llm_meta["llm_latency_ms"] = latency
            llm_meta["llm_provider"] = provider
            llm_meta["llm_used_vision"] = used_vision
            if err:
                llm_meta["llm_error"] = err
            if llm_response:
                steps = llm_response.get("steps", [])
                constraints = llm_response.get("constraints")
                if parse_degraded:
                    llm_meta["text_only_degraded"] = True
                return steps, constraints, llm_meta

    if parse_degraded:
        llm_meta["text_only_degraded"] = True
        llm_meta["llm_error"] = llm_meta.get("llm_error") or "parse_failed_text_only"
        return (
            [
                {
                    "action": "按文字指引操作",
                    "description": (
                        f"未能识别屏幕 UI 元素（GPU parse 超时或失败）。"
                        f"请根据当前界面自行完成：{query}"
                    ),
                    "target_element_id": "",
                }
            ],
            None,
            llm_meta,
        )

    scenario = _choose_scenario(query)
    return (
        _MOCK_FALLBACKS.get(scenario, _MOCK_FALLBACKS["default"]).copy(),
        None,
        llm_meta,
    )


def _assemble_steps(
    raw_steps: List[dict],
    elements: List[UIElement],
) -> List[Step]:
    element_by_id = {e.element_id: e for e in elements}
    steps: List[Step] = []
    for i, raw in enumerate(raw_steps):
        step_index = i + 1
        target_id = raw.get("target_element_id", "")
        element = element_by_id.get(target_id) if target_id else None
        annotation = None
        if element:
            annotation = build_annotation(
                element,
                annotation_type="arrow_highlight" if step_index == 1 else "highlight_only",
                label_text=element.element_id,
            )
        steps.append(
            Step(
                step_index=step_index,
                action=raw["action"],
                description=raw["description"],
                target=raw.get("target"),
                target_element_id=target_id if element else None,
                status="pending",
                annotation=annotation,
                interaction=raw.get("interaction"),
                locate_deferred=raw.get("locate_deferred"),
                prepare_hint=raw.get("prepare_hint"),
            )
        )
    if steps:
        steps[0].status = "active"
        if not steps[0].annotation and elements and not raw_steps[0].get("target_element_id"):
            desc0 = steps[0].description or ""
            act0 = steps[0].action or ""
            if not _is_non_interactive_step(desc0, act0):
                bound_id, bound_ann = _auto_bind_step(act0, desc0, elements)
                if bound_id and bound_ann:
                    steps[0].target_element_id = bound_id
                    steps[0].annotation = bound_ann
        return steps


def _apply_vision_annotations(raw_steps: List[dict], steps: List[Step]) -> None:
    """L4 / L3_DEFERRED：将 raw_steps 上的 Vision annotation 挂到 Step 对象。"""
    for i, raw in enumerate(raw_steps):
        if raw.get("_vision_annotation") and i < len(steps):
            steps[i].annotation = raw["_vision_annotation"]
            steps[i].target_element_id = "~vision"


def _run_omniparser_parse(
    image_base64: str,
    screen_fingerprint: Optional[str],
    latency: LatencyBreakdown,
) -> Tuple[List[UIElement], Optional[str], Optional[List[int]], dict]:
    from server.services.parse_cache import get_cached_parse, put_cached_parse

    if screen_fingerprint:
        cached = get_cached_parse(screen_fingerprint)
        if cached and cached.elements:
            latency.mark_parse(0, cache_hit=True)
            meta = dict(cached.detection_meta or {})
            return (
                cached.elements,
                cached.annotated_image,
                cached.reference_resolution,
                meta,
            )

    with PhaseTimer() as t:
        parse_result = parse_screenshot_full(image_base64)
    latency.mark_parse(t.ms)
    elements: List[UIElement] = []
    meta: dict = {}
    if parse_result.elements:
        elements = parse_result.elements
        meta = parse_result.detection_meta or {}
        if screen_fingerprint:
            put_cached_parse(screen_fingerprint, parse_result)
    else:
        meta["parse_failed"] = True
        meta["parse_degraded"] = True
    return (
        elements,
        parse_result.annotated_image,
        parse_result.reference_resolution,
        meta,
    )


def locate_l4_step(
    step_action: str,
    step_description: str,
    image_base64: str,
    *,
    step_target: Optional[str] = None,
    user_query: Optional[str] = None,
    capture_size: Optional[List[int]] = None,
    upload_size: Optional[List[int]] = None,
    screen_metrics: Optional[dict] = None,
    window_title: Optional[str] = None,
    assist_bundle: Optional[dict] = None,
    latency: Optional[LatencyBreakdown] = None,
) -> Tuple[Optional[Annotation], Optional[List[int]], dict]:
    step = {
        "action": step_action,
        "description": step_description,
        "target": step_target or step_description,
    }
    with PhaseTimer() as t:
        from server.services.assist.adapters.l4 import locate_step_with_assist

        ann, ref, meta = locate_step_with_assist(
            step,
            image_b64=image_base64,
            user_query=user_query or "",
            assist_bundle=assist_bundle,
            capture_size=capture_size,
            upload_size=upload_size,
            screen_metrics=screen_metrics,
            window_title=window_title,
        )
    if latency:
        latency.mark_locate(t.ms)
    return ann, ref, meta


def locate_step_with_vision(
    query: str,
    step_action: str,
    step_description: str,
    image_base64: str,
    latency: Optional[LatencyBreakdown] = None,
) -> Tuple[Optional[Annotation], Optional[List[int]], dict]:
    with PhaseTimer() as t:
        ann, ref, meta = locate_step_target_from_image(
            query, step_action, step_description, image_base64
        )[:3]
    if latency:
        latency.mark_locate(t.ms)
    return ann, ref, meta


def process_query(
    query: str,
    image_base64: Optional[str] = None,
    screen_fingerprint: Optional[str] = None,
    *,
    capture_size: Optional[List[int]] = None,
    upload_size: Optional[List[int]] = None,
    screen_metrics: Optional[dict] = None,
    window_title: Optional[str] = None,
    assist_bundle: Optional[dict] = None,
) -> ProcessResponse:
    started_at = time.perf_counter()
    latency = LatencyBreakdown()

    redline = check_redline(query)
    if redline.triggered:
        return ProcessResponse(
            task_id=str(uuid.uuid4()),
            success=False,
            intent=Intent(
                category="operation_guide",
                summary="请求被拦截",
                reference_type="explicit",
                confidence=1.0,
                needs_clarification=False,
            ),
            ui_elements=[],
            blueprint=Blueprint(name="红线拦截", total_steps=1, current_step=1, state="terminated"),
            steps=[],
            redline=RedlineInfo(
                triggered=True,
                category=redline.category,
                message=redline.message,
                action=redline.action,
            ),
        )

    t_intent = time.perf_counter()
    from server.services.llm_ai import classify_intent, detect_reference_type

    category, summary, confidence = classify_intent(query)
    reference_type = detect_reference_type(query)
    intent = Intent(
        category=category,
        summary=summary,
        reference_type=reference_type,
        confidence=confidence,
        needs_clarification=confidence < 0.80,
    )
    latency.intent_ms = int((time.perf_counter() - t_intent) * 1000)

    complexity = score_complexity(query)
    speed_mode = settings.LLM_SPEED_MODE or "fast"
    l2_steps = generate_l2_steps(query, None)

    t_route = time.perf_counter()
    route = select_route(query, has_image=bool(image_base64), l2_steps=l2_steps)
    latency.route = route
    latency.route_select_ms = int((time.perf_counter() - t_route) * 1000)

    annotated_image: Optional[str] = None
    reference_resolution: Optional[List[int]] = None
    detection_meta: dict = {"complexity": complexity, "llm_speed_mode": speed_mode}
    elements: List[UIElement] = []
    raw_steps: List[dict] = []
    constraints: Optional[dict] = None
    llm_meta: dict = {"route": route}

    if route == "L2":
        raw_steps = l2_steps or []
        llm_meta.update(
            {
                "llm_called": False,
                "llm_speed_mode": speed_mode,
                "llm_used_vision": False,
            }
        )
        latency.mark_parse(0, skipped=True)
    elif route == "BROWSER":
        raw_steps, constraints, llm_meta = generate_browser_plan(query)
        latency.mark_parse(0, skipped=True)
    elif route == "L4":
        with PhaseTimer() as t_plan:
            l4_result = run_l4_process(
                query,
                image_b64=image_base64,
                capture_size=capture_size,
                upload_size=upload_size,
                screen_metrics=screen_metrics,
                window_title=window_title,
                assist_bundle=assist_bundle,
                locate_first_step=bool(image_base64),
            )
        latency.mark_plan(t_plan.ms)
        raw_steps = l4_result.raw_steps
        constraints = l4_result.constraints
        llm_meta = dict(l4_result.llm_meta)
        llm_meta["route"] = "L4"
        llm_meta["llm_called"] = True
        llm_meta["parse_skipped"] = True
        latency.mark_parse(0, skipped=True)
        if l4_result.reference_resolution:
            reference_resolution = l4_result.reference_resolution
        if l4_result.first_step_annotation and raw_steps:
            locate_meta = llm_meta.get("locator_first") or {}
            if locate_meta.get("assist_hit"):
                detection_meta["assist_source"] = locate_meta.get("assist_source")
                detection_meta["assist_hit"] = True
            latency.mark_locate(int(locate_meta.get("latency_ms") or 0))
            idx = int(locate_meta.get("located_step_index", 0))
            if 0 <= idx < len(raw_steps):
                raw_steps[idx]["_vision_annotation"] = l4_result.first_step_annotation
            llm_meta["llm_used_vision"] = True
            llm_meta["locate_latency_ms"] = locate_meta.get("latency_ms")
    elif route == "L3_DEFERRED":
        with PhaseTimer() as t_plan:
            raw_steps, constraints, plan_meta = plan_without_parse(
                query,
                image_base64=image_base64,
                use_vision_hint=False,
            )
        latency.mark_plan(t_plan.ms)
        llm_meta.update(plan_meta)
        llm_meta["route"] = route
        latency.mark_parse(0, skipped=True)

        if image_base64 and raw_steps and route_uses_per_step_locate(route):
            first = raw_steps[0]
            if first.get("interaction") != "keyboard":
                ann, ref, loc_meta = locate_step_with_vision(
                    query,
                    first.get("action", ""),
                    first.get("description", ""),
                    image_base64,
                    latency,
                )
                llm_meta.update(loc_meta)
                if ann and ref:
                    reference_resolution = ref
                    raw_steps[0]["_vision_annotation"] = ann
    elif image_base64:
        elements, annotated_image, reference_resolution, parse_meta = _run_omniparser_parse(
            image_base64, screen_fingerprint, latency
        )
        detection_meta.update(parse_meta)
        parse_degraded = bool(parse_meta.get("parse_degraded"))
        with PhaseTimer() as t_llm:
            raw_steps, constraints, llm_meta = generate_steps(
                query,
                elements,
                annotated_image=annotated_image,
                parse_degraded=parse_degraded,
            )
        latency.llm_ms = t_llm.ms
        llm_meta["route"] = "L3"
    else:
        scenario = _choose_scenario(query)
        elements = SCENARIO_ELEMENTS[scenario].copy()
        raw_steps, constraints, llm_meta = generate_steps(query, elements)
        llm_meta["route"] = "L3"

    detection_meta.update(llm_meta)
    detection_meta.update(latency.to_meta())
    detection_meta["route"] = route
    latency.finalize(started_at)
    detection_meta["latency_breakdown"]["total_ms"] = latency.total_ms

    steps = _assemble_steps(raw_steps, elements)

    if route in ("L4", "L3_DEFERRED"):
        _apply_vision_annotations(raw_steps, steps)

    blueprint = Blueprint(
        name=summary,
        total_steps=len(steps) or 1,
        current_step=1,
        state="executing",
    )

    detection_meta["per_step_locate"] = route_uses_per_step_locate(route)
    detection_meta["omniparser_skipped"] = route_skips_omniparser(route)

    return ProcessResponse(
        task_id=str(uuid.uuid4()),
        success=True,
        intent=intent,
        ui_elements=elements,
        annotated_image=annotated_image,
        blueprint=blueprint,
        steps=steps,
        constraints=constraints,
        reference_resolution=reference_resolution,
        detection_meta=detection_meta,
    )


# ────────────────────────── 重定位 ──────────────────────────

_RELOCATE_PROMPT = """你是一个桌面操作指引助手。

下方是当前屏幕截图中的所有 UI 元素。用户需要找到某个操作对应的元素。

你的任务：从 UI 元素列表中选择**最匹配**用户操作的元素的 `element_id`。

## 当前屏幕 UI 元素
{element_list}

## 输出格式
严格按以下 JSON 返回，不要 markdown 代码块：
{{
  "target_element_id": "~3",
  "confidence": 0.85
}}

规则：
1. 如果当前屏幕有匹配的元素，返回该元素的 `element_id` 和置信度。
2. 如果当前屏幕依然没有对应元素（如步骤是"等待下载完成"），`target_element_id` 为空字符串 `""`，`confidence` 为 0.0。
3. 优先选择 `text` 字段语义最接近的元素；其次看 `type` 匹配（button/input/icon）。
4. 置信度低于 0.60 时，`target_element_id` 应为空。"""


def _is_non_interactive_step(description: str, action: str) -> bool:
    text = f"{description} {action}"
    return any(k in text for k in ("等待", "稍候", "加载中", "完成后"))


def _auto_bind_step(
    action: str,
    description: str,
    elements: List[UIElement],
) -> Tuple[Optional[str], Optional[Annotation]]:
    result = _text_match_element(description, action, elements)
    if not result:
        return None, None
    matched, score = result
    if score < 0.15:
        return None, None
    annotation = build_annotation(
        matched,
        annotation_type="arrow_highlight",
        label_text=matched.element_id,
    )
    return matched.element_id, annotation


def _text_match_element(
    description: str, action: str, elements: List[UIElement]
) -> Optional[Tuple[UIElement, float]]:
    from server.services.assist.text_match import text_match_element

    return text_match_element(description, action, elements)


def relocate_step(
    step_action: str,
    step_description: str,
    image_base64: str,
    *,
    query: str = "",
    use_vision: bool = False,
) -> Tuple[Optional[str], Optional[Annotation], List[UIElement], Optional[List[int]]]:
    if use_vision:
        ann, ref, _ = locate_step_with_vision(
            query or step_description,
            step_action,
            step_description,
            image_base64,
        )
        return "~vision" if ann else None, ann, [], ref

    elements = parse_screenshot(image_base64)
    if not elements:
        return None, None, [], None

    target_id: Optional[str] = None
    matched_element: Optional[UIElement] = None

    if settings.USE_REAL_LLM:
        from server.services.perception import serialize_elements

        relocate_prompt = _RELOCATE_PROMPT.format(element_list=serialize_elements(elements))
        relocate_result, _, _, _, _ = call_deepseek(
            query=f"请为步骤「{step_description}」（动作：{step_action}）匹配最合适的元素",
            elements=None,
            system_prompt=relocate_prompt,
            temperature=0.1,
            max_tokens=2000,
            speed_mode="fast",
        )
        if relocate_result:
            candidate_id = relocate_result.get("target_element_id", "")
            if candidate_id:
                element_by_id = {e.element_id: e for e in elements}
                matched_element = element_by_id.get(candidate_id)
                if matched_element:
                    target_id = candidate_id

    if not matched_element:
        result = _text_match_element(step_description, step_action, elements)
        if result:
            matched_element, _ = result
            target_id = matched_element.element_id

    annotation: Optional[Annotation] = None
    if matched_element:
        annotation = build_annotation(
            matched_element,
            annotation_type="arrow_highlight",
            label_text=matched_element.element_id,
        )

    return target_id, annotation, elements, None
