"""
规划路由层（P0 + P2 核心实现区）— 纯视觉 LLM 管道版本

移除 OmniParser 依赖，截图直接发给多模态 LLM。
LLM 看图理解界面、生成步骤并用 [POINT:x,y:label] 标记位置。
"""
import uuid
from typing import List, Optional

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
from server.services.redline_service import check_redline
from server.services.planning.complexity_router import score_complexity, generate_l2_steps
from server.services.agent.orchestrator import orchestrator
from server.services.validation.coords import normalize_coordinate, clamp_to_bounds
from server.services.validation.postprocess import postprocess_pointer


# ═══════════════════════════════════════════════════════════════════════════
# Mock fallbacks — used when LLM is unavailable
# ═══════════════════════════════════════════════════════════════════════════

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


def _choose_scenario(query: str) -> str:
    """根据查询选择场景"""
    q = query.lower()
    if any(k in q for k in ["微信", "qq", "软件", "下载", "安装"]):
        return "wechat"
    if any(k in q for k in ["截图", "截屏", "snip"]):
        return "screenshot"
    return "default"


# ═══════════════════════════════════════════════════════════════════════════
# Annotation builder — from LLM [POINT] coordinates
# ═══════════════════════════════════════════════════════════════════════════

def _build_annotation_from_pointer(
    pointer: dict,
    screen_w: int = 1920,
    screen_h: int = 1080,
    label_text: str = "element",
    annotation_type: str = "arrow_highlight",
) -> Optional[Annotation]:
    """Build an Annotation from LLM pointer coordinates (0-1000 normalized).

    Args:
        pointer: Dict with 'x', 'y', 'label' (0-1000 normalized)
        screen_w, screen_h: Screen dimensions in pixels
        label_text: Label for the annotation
        annotation_type: 'arrow_highlight' or 'highlight_only'

    Returns:
        Annotation object, or None if pointer has no valid coordinates
    """
    x = pointer.get("x") if pointer else None
    y = pointer.get("y") if pointer else None

    if x is None or y is None:
        return None

    # Normalize 0-1000 -> absolute pixels
    abs_x, abs_y = normalize_coordinate(float(x), float(y), screen_w, screen_h)

    # Clamp to bounds
    abs_x, abs_y, _ = clamp_to_bounds(abs_x, abs_y, screen_w, screen_h, margin=10)

    # Create annotation with a small bounding box around the point
    bbox_size = 40
    bbox = [
        max(0, abs_x - bbox_size // 2),
        max(0, abs_y - bbox_size // 2),
        min(screen_w, abs_x + bbox_size // 2),
        min(screen_h, abs_y + bbox_size // 2),
    ]

    return Annotation(
        type=annotation_type,
        bbox=bbox,
        center=[abs_x, abs_y],
        label=label_text,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Main process_query — pure vision LLM pipeline
# ═══════════════════════════════════════════════════════════════════════════

def process_query(
    query: str,
    image_base64: Optional[str] = None,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> ProcessResponse:
    """处理用户查询，生成完整的 ProcessResponse。

    纯视觉 LLM 管道：截图直接发给多模态 LLM，无需 OmniParser。

    Args:
        query: 用户原始查询
        image_base64: Base64 编码截图（可选）
        screen_width: 屏幕宽度（用于坐标映射）
        screen_height: 屏幕高度（用于坐标映射）

    Returns:
        完整的处理响应
    """
    # 0. 红线检测
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
            blueprint=Blueprint(
                name="红线拦截",
                total_steps=1,
                current_step=1,
                state="terminated",
            ),
            steps=[],
            redline=RedlineInfo(
                triggered=True,
                category=redline.category,
                message=redline.message,
                action=redline.action,
            ),
        )

    # 1. 意图分类（保留现有 SetFit 逻辑）
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

    # ── L2/L3 路由 ──
    complexity = score_complexity(query)
    route = "L2" if complexity < 30 else "L3"

    raw_steps: Optional[List[dict]] = None
    constraints: Optional[dict] = None
    ui_elements: List[UIElement] = []
    annotated_image: Optional[str] = None
    reference_resolution: Optional[List[int]] = [screen_width, screen_height]
    detection_meta: Optional[dict] = {
        "route": route,
        "complexity": complexity,
        "backend": "vision_llm",
    }

    # L2 快路径：本地模板匹配（不需要 LLM）
    if route == "L2":
        raw_steps = generate_l2_steps(query, ui_elements)

    # L3 / L2 未命中降级：调用视觉 LLM
    if not raw_steps:
        route = "L3"
        detection_meta["route"] = "L3"

        # 优先使用 orchestrator（Plan+Locate 组合模式）
        if settings.USE_REAL_LLM and image_base64:
            try:
                result = orchestrator.process_query(
                    query=query,
                    image_base64=image_base64,
                    screen_width=screen_width,
                    screen_height=screen_height,
                )

                if result.get("success") and result.get("plan"):
                    plan = result["plan"]
                    pointer = result.get("pointer") or {}

                    # Convert orchestrator step format to HAJIMI Step schema
                    steps: List[Step] = []
                    for i, ps in enumerate(plan.get("steps", [])):
                        step_index = i + 1
                        # Build annotation from pointer if this is the first step
                        annotation = None
                        if i == 0 and pointer.get("x") is not None:
                            annotation = _build_annotation_from_pointer(
                                pointer,
                                screen_w=screen_width,
                                screen_h=screen_height,
                                label_text=pointer.get("label", f"Step {step_index}"),
                                annotation_type="arrow_highlight",
                            )

                        steps.append(Step(
                            step_index=step_index,
                            action=ps.get("title", f"Step {step_index}"),
                            description=ps.get("instruction", ""),
                            target_element_id=f"~step_{step_index}" if annotation else None,
                            status="active" if i == 0 else "pending",
                            annotation=annotation,
                        ))

                    blueprint = Blueprint(
                        name=plan.get("goal", summary),
                        total_steps=len(steps),
                        current_step=1,
                        state="pending_confirm",
                    )

                    # Extract reply text without [POINT] tag
                    from server.services.llm.providers import parse_point_tags
                    reply = result.get("reply", "")
                    parsed = parse_point_tags(reply)

                    return ProcessResponse(
                        task_id=str(uuid.uuid4()),
                        success=True,
                        intent=intent,
                        ui_elements=ui_elements,
                        annotated_image=image_base64,  # Pass original image
                        blueprint=blueprint,
                        steps=steps,
                        constraints=constraints,
                        reference_resolution=reference_resolution,
                        detection_meta=detection_meta,
                    )

            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Orchestrator failed: {e}, falling back to legacy LLM path"
                )

        # Legacy fallback: direct LLM call with old prompt format
        if settings.USE_REAL_LLM:
            from server.services.llm.client import call_deepseek
            llm_response = call_deepseek(
                query,
                elements=None,  # No pre-detected elements
                image_base64=image_base64,
                timeout=settings.LLM_TIMEOUT,
            )
            if llm_response:
                raw_steps = llm_response.get("steps", [])
                constraints = llm_response.get("constraints")

    # Fallback to mock data if no steps generated
    if not raw_steps:
        scenario = _choose_scenario(query)
        raw_steps = _MOCK_FALLBACKS.get(scenario, _MOCK_FALLBACKS["default"]).copy()

    # ── 构建 Step 列表 ──
    steps: List[Step] = []
    for i, raw in enumerate(raw_steps):
        step_index = i + 1
        target_id = raw.get("target_element_id", "")
        annotation = None

        if target_id:
            annotation = Annotation(
                type="arrow_highlight" if step_index == 1 else "highlight_only",
                bbox=[100, 100, 200, 140],
                center=[150, 120],
                label=target_id,
            )

        steps.append(Step(
            step_index=step_index,
            action=raw.get("action", f"Step {step_index}"),
            description=raw.get("description", ""),
            target_element_id=target_id if target_id else None,
            status="active" if step_index == 1 else "pending",
            annotation=annotation,
        ))

    blueprint = Blueprint(
        name=summary,
        total_steps=len(steps),
        current_step=1,
        state="pending_confirm",
    )

    return ProcessResponse(
        task_id=str(uuid.uuid4()),
        success=True,
        intent=intent,
        ui_elements=ui_elements,
        annotated_image=image_base64,
        blueprint=blueprint,
        steps=steps,
        constraints=constraints,
        reference_resolution=reference_resolution,
        detection_meta=detection_meta,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Relocate — pure vision LLM version
# ═══════════════════════════════════════════════════════════════════════════

def relocate_step(
    step_action: str,
    step_description: str,
    image_base64: str,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> tuple:
    """对新截图重定位指定步骤。纯视觉 LLM 匹配。

    Returns:
        (target_element_id, annotation, all_elements)
    """
    from server.services.agent.chains import locate_step_target

    if not settings.USE_REAL_LLM:
        return None, None, []

    try:
        pointer = locate_step_target(
            goal=step_description,
            step={"title": step_action, "instruction": step_description},
            image_base64=image_base64,
            force_point=True,
            provider=None,
        )

        if pointer.get("x") is not None and pointer.get("y") is not None:
            target_id = f"~{step_action[:10]}"
            annotation = _build_annotation_from_pointer(
                pointer,
                screen_w=screen_width,
                screen_h=screen_height,
                label_text=pointer.get("label", step_action[:20]),
                annotation_type="arrow_highlight",
            )
            return target_id, annotation, []

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Relocate LLM call failed: {e}")

    return None, None, []


# ═══════════════════════════════════════════════════════════════════════════
# Legacy compatibility: generate_steps (used by tests)
# ═══════════════════════════════════════════════════════════════════════════

def generate_steps(
    query: str,
    elements: Optional[List[UIElement]] = None,
    annotated_image: Optional[str] = None,
) -> tuple:
    """生成操作步骤与约束条件（兼容旧接口）。

    优先级：LLM > mock fallback
    """
    if settings.USE_REAL_LLM:
        from server.services.llm.client import call_deepseek
        llm_response = call_deepseek(
            query,
            elements=elements,
            image_base64=annotated_image,
            timeout=settings.LLM_TIMEOUT,
        )
        if llm_response:
            steps = llm_response.get("steps", [])
            constraints = llm_response.get("constraints")
            return steps, constraints

    scenario = _choose_scenario(query)
    return _MOCK_FALLBACKS.get(scenario, _MOCK_FALLBACKS["default"]).copy(), None
