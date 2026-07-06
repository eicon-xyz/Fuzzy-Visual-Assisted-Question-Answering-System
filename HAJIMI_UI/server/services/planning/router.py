"""
规划路由层 — 红线检测 → 意图分类 → Planning Agent → 首帧截图

Runway: redline → intent → plan → screenshot (display-only).
Execution happens later via ExecutionAgent in the engine.
"""

import logging
import uuid
from typing import List, Optional

from server.models.schemas import (
    Blueprint,
    ExecutedStep,
    Intent,
    PlanningStep,
    ProcessResponse,
    RedlineInfo,
    UIElement,
)
from server.services.redline_service import check_redline

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Mock fallbacks
# ═══════════════════════════════════════════════════════════════════════════

_MOCK_FALLBACKS = {
    "wechat": [
        {
            "action": "click",
            "description": "打开浏览器",
            "bbox_center": [150, 375],
            "params": None,
        },
        {
            "action": "type",
            "description": "输入微信官网地址",
            "bbox_center": [500, 70],
            "params": "weixin.qq.com",
        },
        {
            "action": "click",
            "description": "点击下载按钮",
            "bbox_center": [480, 525],
            "params": None,
        },
        {
            "action": "click",
            "description": "运行安装程序",
            "bbox_center": [130, 630],
            "params": None,
        },
    ],
    "notepad": [
        {
            "action": "press_key",
            "description": "按Win+R打开运行窗口",
            "bbox_center": None,
            "params": "win+r",
        },
        {
            "action": "type",
            "description": "输入notepad",
            "bbox_center": None,
            "params": "notepad",
        },
        {
            "action": "press_key",
            "description": "按回车启动记事本",
            "bbox_center": None,
            "params": "enter",
        },
    ],
    "calculator": [
        {
            "action": "press_key",
            "description": "按Win+R打开运行窗口",
            "bbox_center": None,
            "params": "win+r",
        },
        {
            "action": "type",
            "description": "输入calc",
            "bbox_center": None,
            "params": "calc",
        },
        {
            "action": "press_key",
            "description": "按回车启动计算器",
            "bbox_center": None,
            "params": "enter",
        },
    ],
    "screenshot": [
        {
            "action": "press_key",
            "description": "打开截图工具",
            "bbox_center": None,
            "params": "win+shift+s",
        },
        {
            "action": "click",
            "description": "选择截图区域",
            "bbox_center": [500, 300],
            "params": None,
        },
        {
            "action": "click",
            "description": "保存截图",
            "bbox_center": [200, 600],
            "params": None,
        },
    ],
    "default": [
        {
            "action": "wait",
            "description": "等待界面加载",
            "bbox_center": None,
            "params": 2,
        },
        {
            "action": "click",
            "description": "点击目标元素",
            "bbox_center": [500, 300],
            "params": None,
        },
    ],
}


def _choose_scenario(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["微信", "qq", "软件", "下载", "安装"]):
        return "wechat"
    if any(k in q for k in ["记事本", "notepad", "文本"]):
        return "notepad"
    if any(k in q for k in ["计算器", "calc", "calculator"]):
        return "calculator"
    if any(k in q for k in ["截图", "截屏", "snip"]):
        return "screenshot"
    return "default"


# ═══════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════


def process_query(
    query: str,
    image_base64: Optional[str] = None,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> ProcessResponse:
    """
    Planning phase: redline → intent → Planning Agent → first screenshot.
    Execution happens in engine via ExecutionAgent.
    """
    # 0. Redline check (unchanged)
    redline = check_redline(query)
    if redline.triggered:
        return ProcessResponse(
            task_id=str(uuid.uuid4()),
            success=False,
            goal="",
            intent=Intent(
                category="operation_guide",
                summary="请求被拦截",
                reference_type="explicit",
                confidence=1.0,
                needs_clarification=False,
            ),
            ui_elements=[],
            annotated_image=None,
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

    # 1. Intent classification (unchanged)
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

    # 2. Planning Agent + OmniParser run in parallel (they are independent)
    import concurrent.futures

    from server.services.planning.planner import PlanningResult, plan_steps

    plan_result = None

    def _call_planner():
        nonlocal plan_result
        try:
            plan_result = plan_steps(query)
        except Exception as e:
            logger.error(f"Planning Agent failed: {e}")
            plan_result = PlanningResult(
                goal=query,
                steps=[PlanningStep(step_index=1, instruction=query)],
            )

    planner_future = None
    ui_elements: List[UIElement] = []
    annotated_image: Optional[str] = image_base64
    detection_meta: dict = {"backend": "omniparser", "route": "L3"}
    parse_result_temp = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        planner_future = executor.submit(_call_planner)
        # While Planning Agent runs, start OmniParser in main thread
        if image_base64:
            try:
                from server.services.omniparser_client import parse_screenshot_full

                parse_result_temp = parse_screenshot_full(image_base64)
                ui_elements = parse_result_temp.elements
                annotated_image = parse_result_temp.annotated_image or image_base64
                detection_meta.update(parse_result_temp.detection_meta or {})
            except Exception as e:
                logger.error(f"OmniParser initial scan failed: {e}")
        planner_future.result(timeout=30)

    goal = plan_result.goal
    planning_steps = plan_result.steps

    # 3. Convert PlanningStep → ExecutedStep (all pending)
    executed_steps: List[ExecutedStep] = []
    for ps in planning_steps:
        executed_steps.append(
            ExecutedStep(
                step_index=ps.step_index,
                instruction=ps.instruction,
                status="pending",
            )
        )

    # 4. These are populated during the parallel section above

    # 5. Build response
    blueprint = Blueprint(
        name=goal[:40] if goal else summary,
        total_steps=len(executed_steps),
        current_step=1,
        state="generated",
    )

    return ProcessResponse(
        task_id=str(uuid.uuid4()),
        success=True,
        goal=goal,
        intent=intent,
        ui_elements=ui_elements,
        annotated_image=annotated_image,
        blueprint=blueprint,
        steps=executed_steps,
        detection_meta=detection_meta,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 兼容旧接口
# ═══════════════════════════════════════════════════════════════════════════


def generate_steps(
    query: str,
    elements: Optional[List[UIElement]] = None,
    annotated_image: Optional[str] = None,
):
    """
    [兼容] 生成操作步骤 — 供旧测试使用。
    不调用 OmniParser，需要外部传入元素。
    """
    scenario = _choose_scenario(query)
    return _MOCK_FALLBACKS.get(scenario, _MOCK_FALLBACKS["default"]).copy(), None


def relocate_step(
    step_action: str,
    step_description: str,
    image_base64: str,
    screen_width: int = 1920,
    screen_height: int = 1080,
):
    """
    对当前屏幕重定位指定步骤（用于操作失败后的恢复）。
    调用 OmniParser 重新检测元素 → 匹配最接近的元素。
    """
    try:
        from server.services.omniparser_client import parse_screenshot_full

        parse_result = parse_screenshot_full(image_base64)
        elements = parse_result.elements
    except Exception:
        return None, None, []

    if not elements:
        return None, None, []

    # 找最相关元素：优先 text 匹配，否则 type=button 优先级最高
    best = None
    best_score = 0
    for el in elements:
        score = 0
        if el.text and any(w in el.text for w in step_description[:10]):
            score += 3
        if el.element_type in ("button", "icon"):
            score += 2
        if el.confidence > 0.7:
            score += 1
        if score > best_score:
            best_score = score
            best = el

    if best:
        bbox = best.bbox
        return (
            best.element_id,
            {"type": "highlight_only", "highlight_bbox": [int(v) for v in bbox]},
            [e.model_dump() for e in elements],
        )
    return None, None, []
