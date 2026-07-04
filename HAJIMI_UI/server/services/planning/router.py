"""
规划路由层（P0 + P2 核心实现区）
负责：步骤生成、步骤与元素语义绑定、ProcessResponse 组装、重定位
"""
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
from server.services.llm import call_deepseek
from server.services.omniparser_client import parse_screenshot, parse_screenshot_full
from server.services.planning.annotation import build_annotation
from server.services.redline_service import check_redline
from server.services.planning.complexity_router import score_complexity, generate_l2_steps


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
    """根据查询选择场景"""
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
) -> tuple[List[dict], Optional[dict]]:
    """
    生成操作步骤与约束条件，优先使用 LLM，失败 fallback 到 mock 数据

    Args:
        query: 用户原始查询
        elements: 当前屏幕 UI 元素列表
        annotated_image: SoM 标注图 base64（可选，传入时 LLM 可看图识别元素）

    Returns:
        (步骤字典列表, 约束条件字典或 None)
    """
    if settings.USE_REAL_LLM:
        llm_response = call_deepseek(
            query,
            elements=elements,
            image_base64=annotated_image,
        )
        if llm_response:
            steps = llm_response.get("steps", [])
            constraints = llm_response.get("constraints")
            return steps, constraints

    scenario = _choose_scenario(query)
    # mock fallback 默认无约束
    return _MOCK_FALLBACKS.get(scenario, _MOCK_FALLBACKS["default"]).copy(), None


def process_query(query: str, image_base64: Optional[str] = None) -> ProcessResponse:
    """
    处理用户查询，生成完整的 ProcessResponse

    Args:
        query: 用户原始查询
        image_base64: Base64 编码截图（可选）

    Returns:
        完整的处理响应
    """
    # 0. 红线检测 — 在所有处理之前拦截违规请求
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

    # 1. 复用已冻结的意图与指代逻辑，避免重复实现
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

    # ── L2/L3 路由：先评分，后续元素解析和步骤生成据此分流 ──
    complexity = score_complexity(query)
    route = "L2" if complexity < 30 else "L3"

    # 获取元素：优先 OmniParser 真实解析，失败则用场景 mock
    annotated_image: Optional[str] = None
    reference_resolution: Optional[List[int]] = None
    detection_meta: Optional[dict] = None

    if image_base64:
        parse_result = parse_screenshot_full(image_base64)
        if parse_result.elements:
            elements = parse_result.elements
            annotated_image = parse_result.annotated_image
            reference_resolution = parse_result.reference_resolution
            detection_meta = parse_result.detection_meta
            if detection_meta:
                detection_meta['route'] = route
                detection_meta['complexity'] = complexity
        else:
            scenario = _choose_scenario(query)
            elements = SCENARIO_ELEMENTS[scenario].copy()
    else:
        scenario = _choose_scenario(query)
        elements = SCENARIO_ELEMENTS[scenario].copy()
        detection_meta = detection_meta or {}
        detection_meta['route'] = route
        detection_meta['complexity'] = complexity

    raw_steps: Optional[List[dict]] = None
    constraints: Optional[dict] = None

    if route == "L2":
        # L2 快路径：本地模板匹配
        raw_steps = generate_l2_steps(query, elements)

    if not raw_steps:
        # L3 慢路径（或 L2 模板未命中降级）：调用 LLM
        route = "L3"
        raw_steps, constraints = generate_steps(
            query, elements, annotated_image=annotated_image
        )
        if raw_steps is None:
            raw_steps = []

    # ── 按 element_id 索引元素，实现语义绑定 ──
    element_by_id = {e.element_id: e for e in elements}

    steps: List[Step] = []
    for i, raw in enumerate(raw_steps):
        step_index = i + 1
        target_id = raw.get("target_element_id", "")
        element = element_by_id.get(target_id) if target_id else None

        if element:
            annotation = build_annotation(
                element,
                annotation_type="arrow_highlight" if step_index == 1 else "highlight_only",
                label_text=element.element_id,
            )
        else:
            annotation = None

        steps.append(
            Step(
                step_index=step_index,
                action=raw["action"],
                description=raw["description"],
                target_element_id=target_id if element else None,
                status="pending",
                annotation=annotation,
            )
        )

    if steps:
        steps[0].status = "active"

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


def _text_match_element(
    description: str, action: str, elements: List[UIElement]
) -> Optional[Tuple[UIElement, float]]:
    """简单文本匹配 fallback，找不到时返回 None"""
    keywords = set(description.lower().split() + action.lower().split())
    best: Optional[Tuple[UIElement, float]] = None
    for e in elements:
        text = (e.text or "").lower()
        if not text:
            continue
        # 计算关键词命中率
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            score = hits / max(len(keywords), 1)
            if best is None or score > best[1]:
                best = (e, score)
    return best


def relocate_step(
    step_action: str,
    step_description: str,
    image_base64: str,
) -> Tuple[Optional[str], Optional[Annotation], List[UIElement]]:
    """
    对新截图重定位指定步骤，返回匹配的 element_id、标注、全量元素列表。

    Args:
        step_action: 步骤的动作（如"点击下载按钮"）
        step_description: 步骤的详细描述
        image_base64: 新截图的 Base64

    Returns:
        (target_element_id, annotation, all_elements)
    """
    elements = parse_screenshot(image_base64)
    if not elements:
        return None, None, []

    target_id: Optional[str] = None
    matched_element: Optional[UIElement] = None

    # 1) 尝试 LLM 匹配
    if settings.USE_REAL_LLM:
        from server.services.perception import serialize_elements
        relocate_prompt = _RELOCATE_PROMPT.format(element_list=serialize_elements(elements))
        relocate_result = call_deepseek(
            query=f"请为步骤「{step_description}」（动作：{step_action}）匹配最合适的元素",
            elements=None,  # elements already embedded in formatted prompt
            system_prompt=relocate_prompt,
            temperature=0.1,
            max_tokens=2000,
            timeout=settings.LLM_TIMEOUT or settings.DEEPSEEK_TIMEOUT,
        )
        if relocate_result:
            candidate_id = relocate_result.get("target_element_id", "")
            if candidate_id:
                element_by_id = {e.element_id: e for e in elements}
                matched_element = element_by_id.get(candidate_id)
                if matched_element:
                    target_id = candidate_id

    # 2) Fallback: 文本关键词匹配
    if not matched_element:
        result = _text_match_element(step_description, step_action, elements)
        if result:
            matched_element, _ = result
            target_id = matched_element.element_id

    # 3) 构建标注
    annotation: Optional[Annotation] = None
    if matched_element:
        annotation = build_annotation(
            matched_element,
            annotation_type="arrow_highlight",
            label_text=matched_element.element_id,
        )

    return target_id, annotation, elements
