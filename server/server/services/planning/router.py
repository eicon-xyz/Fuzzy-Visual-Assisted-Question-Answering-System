"""
规划路由层 — OpenGuider 风格架构
核心：截图直接发给多模态 LLM 看图定位，不依赖 OmniParser。
LLM 返回 [POINT:x,y:label] 格式的坐标标注。
"""
import re
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
from server.services.redline_service import check_redline
from server.services.planning.complexity_router import score_complexity, generate_l2_steps
from server.services.planning.vision_prompt import VISION_LOCATOR_PROMPT

_RELOCATE_VISION_PROMPT = """You are helping locate a UI element on a screenshot.
Look at the screenshot. Find the element that matches this step:
Step: {step_action}
Description: {step_description}

If the element IS visible, return:
{{"target_element_id": "found", "x": 500, "y": 300, "label": "element name", "confidence": 0.9}}

x and y are normalized 0-1000 coordinates.
If NOT visible, return:
{{"target_element_id": "", "x": 0, "y": 0, "label": "", "confidence": 0.0}}

Return ONLY valid JSON, no markdown."""

# ── POINT 标签解析 ──

_POINT_RE = re.compile(
    r'\[POINT:\s*([\d.]+)\s*,\s*([\d.]+)\s*(?::\s*([^\]:]+))?\s*\]',
    re.IGNORECASE,
)


def parse_point_tags(text: str) -> List[dict]:
    """从文本中解析所有 [POINT:x,y:label] 标签，返回坐标列表。"""
    results = []
    for m in _POINT_RE.finditer(text):
        x, y = float(m.group(1)), float(m.group(2))
        label = (m.group(3) or "").strip()
        results.append({"x": x, "y": y, "label": label})
    return results


def strip_point_tags(text: str) -> str:
    """移除文本中的 [POINT:...] 标签，返回干净文本。"""
    return _POINT_RE.sub("", text).strip()


# ── 归一化坐标 → 屏幕像素 ──

def normalize_coordinate(norm_x: float, norm_y: float, screen_w: int, screen_h: int) -> Tuple[int, int]:
    """
    OpenGuider 风格坐标归一化。
    0-1000 归一化坐标 → 实际屏幕像素。
    如果值 <=1.0 则视为 0-1 比例。
    """
    if norm_x <= 1.0 and norm_y <= 1.0:
        # 0-1 比例坐标
        return int(round(norm_x * screen_w)), int(round(norm_y * screen_h))
    # 0-1000 归一化坐标
    return int(round(norm_x / 1000.0 * screen_w)), int(round(norm_y / 1000.0 * screen_h))


# ── 简单文本匹配（用于 L2 模板 + 真实元素的 fallback） ──

def _text_match_element(
    description: str, action: str, elements: List[UIElement]
) -> Optional[Tuple[UIElement, float]]:
    keywords = set(description.lower().split() + action.lower().split())
    best: Optional[Tuple[UIElement, float]] = None
    for e in elements:
        text = (e.text or "").lower()
        if not text:
            continue
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            score = hits / max(len(keywords), 1)
            if best is None or score > best[1]:
                best = (e, score)
    return best


def _is_keyboard_only_step(action: str, description: str) -> bool:
    keyboard_patterns = [
        "Ctrl+", "Win+", "Alt+", "Shift+",
        "按下", "按 ", "快捷键", "回车", "Enter",
    ]
    combined = f"{action} {description}"
    for p in keyboard_patterns:
        if p in combined:
            return True
    return False


def _bind_l2_steps_to_elements(raw_steps: List[dict], elements: List[UIElement]):
    for step in raw_steps:
        if step.get("target_element_id"):
            continue
        action = step.get("action", "")
        desc = step.get("description", "")
        if _is_keyboard_only_step(action, desc):
            continue
        result = _text_match_element(desc, action, elements)
        if result:
            matched_element, score = result
            if score >= 0.25:
                step["target_element_id"] = matched_element.element_id


def _any_step_bound(raw_steps: List[dict]) -> bool:
    for step in raw_steps:
        if step.get("target_element_id"):
            return True
    return False


# ── 场景 mock ──

SCENARIO_ELEMENTS = {
    "wechat": [
        UIElement(element_id="~1", bbox=[120, 340, 240, 380], element_type="icon",
                  text="Microsoft Edge", confidence=0.95, center=[180, 360]),
        UIElement(element_id="~2", bbox=[860, 620, 1020, 660], element_type="button",
                  text="下载", confidence=0.91, center=[940, 640]),
    ],
    "default": [
        UIElement(element_id="~1", bbox=[100, 100, 200, 140], element_type="button",
                  text="开始", confidence=0.90, center=[150, 120]),
    ],
}

_MOCK_FALLBACKS = {
    "wechat": [
        {"action": "打开浏览器", "description": "找到桌面上的浏览器图标，双击打开。", "target_element_id": "~1"},
        {"action": "访问微信官网", "description": "在地址栏输入 weixin.qq.com 并回车。", "target_element_id": ""},
        {"action": "点击下载按钮", "description": "在官网首页找到「下载」按钮并点击。", "target_element_id": "~2"},
        {"action": "运行安装程序", "description": "下载完成后，双击安装包按提示完成安装。", "target_element_id": ""},
    ],
    "default": [
        {"action": "观察当前界面", "description": "仔细查看屏幕上的可点击元素。", "target_element_id": "~1"},
        {"action": "按提示操作", "description": "根据系统指引逐步完成目标。", "target_element_id": ""},
    ],
}


def _choose_scenario(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["微信", "qq", "软件", "下载", "安装"]):
        return "wechat"
    return "default"


# ══════════════════════════════════════════════════════
#  OpenGuider 风格步骤生成：直接看图 + 返回 [POINT]
# ══════════════════════════════════════════════════════

def generate_steps_vision(
    query: str,
    image_base64: Optional[str] = None,
) -> Optional[List[dict]]:
    """
    OpenGuider 风格：截图直接发给多模态 LLM，看图返回步骤+坐标。
    无 OmniParser 依赖。
    """
    if not settings.USE_REAL_LLM or not image_base64:
        return None

    llm_response = call_deepseek(
        query=query,
        elements=None,           # 不传元素列表，LLM 直接看图
        image_base64=image_base64,
        system_prompt=VISION_LOCATOR_PROMPT,
        temperature=0.3,
        max_tokens=4096,
        timeout=120,
    )
    if llm_response:
        return llm_response.get("steps", [])
    return None


# ══════════════════════════════════════════════════════
#  主入口：process_query
# ══════════════════════════════════════════════════════

def process_query(query: str, image_base64: Optional[str] = None) -> ProcessResponse:
    # 0. 红线检测
    redline = check_redline(query)
    if redline.triggered:
        return ProcessResponse(
            task_id=str(uuid.uuid4()), success=False,
            intent=Intent(category="operation_guide", summary="请求被拦截",
                          reference_type="explicit", confidence=1.0, needs_clarification=False),
            ui_elements=[], blueprint=Blueprint(name="红线拦截", total_steps=1, current_step=1, state="terminated"),
            steps=[], redline=RedlineInfo(triggered=True, category=redline.category,
                                          message=redline.message, action=redline.action),
        )

    # 1. 意图分类
    from server.services.llm_ai import classify_intent, detect_reference_type
    category, summary, confidence = classify_intent(query)
    reference_type = detect_reference_type(query)
    intent = Intent(category=category, summary=summary, reference_type=reference_type,
                    confidence=confidence, needs_clarification=confidence < 0.80)

    # 2. 屏幕分辨率（从截图提取或使用默认值）
    screen_w, screen_h = 1920, 1080
    if image_base64:
        try:
            import base64
            from io import BytesIO
            from PIL import Image
            raw = image_base64
            if "," in raw and raw.startswith("data:"):
                raw = raw.split(",", 1)[1]
            img = Image.open(BytesIO(base64.b64decode(raw)))
            screen_w, screen_h = img.size
        except Exception:
            pass

    # 3. 首选：OpenGuider 风格视觉定位（截图 → LLM → steps + [POINT]）
    raw_steps = None
    constraints = None
    use_vision = bool(image_base64 and settings.USE_REAL_LLM)

    if use_vision:
        raw_steps = generate_steps_vision(query, image_base64)

    # 4. Fallback：L2 模板（无图或 LLM 不可用时）
    if not raw_steps:
        scenario = _choose_scenario(query)
        elements = SCENARIO_ELEMENTS.get(scenario, SCENARIO_ELEMENTS["default"]).copy()
        raw_steps = generate_l2_steps(query, elements)
        if raw_steps and elements:
            _bind_l2_steps_to_elements(raw_steps, elements)
        if not raw_steps:
            raw_steps = _MOCK_FALLBACKS.get(scenario, _MOCK_FALLBACKS["default"]).copy()

    if raw_steps is None:
        raw_steps = []

    # 5. 构建 Step 对象：从 [POINT] 标签或 mock 元素提取 annotation
    steps: List[Step] = []
    # 重新获取 mock 元素用于 fallback 绑定
    scenario = _choose_scenario(query)
    elements = SCENARIO_ELEMENTS.get(scenario, SCENARIO_ELEMENTS["default"]).copy()
    element_by_id = {e.element_id: e for e in elements}

    from server.services.planning.annotation import build_annotation
    from server.services.planning.risk_scorer import score_step

    for i, raw in enumerate(raw_steps):
        step_index = i + 1
        desc = raw.get("description", "")
        annotation = None

        # 尝试从 [POINT] 标签提取坐标
        points = parse_point_tags(desc) if desc else []
        clean_desc = strip_point_tags(desc) if desc else desc

        if points:
            # 使用第一个 POINT 坐标构建 annotation
            p = points[0]
            px, py = normalize_coordinate(p["x"], p["y"], screen_w, screen_h)
            label = p.get("label") or raw.get("action", "")
            # 构造一个 40x40 的虚拟 bbox 围绕点击位置
            half = 20
            bbox = [px - half, py - half, px + half, py + half]
            annotation = Annotation(
                type="arrow_highlight" if step_index == 1 else "highlight_only",
                highlight_bbox=bbox,
                arrow_to=[px, py],
                arrow_from=[px, max(0, py - 100)],
                label_position=[bbox[0], max(0, bbox[1] - 44)],
                label_text=label,
                confidence=0.85,
            )
        else:
            # Fallback: 尝试通过 target_element_id 绑定到 mock 元素
            target_id = raw.get("target_element_id", "")
            element = element_by_id.get(target_id) if target_id else None
            if element:
                annotation = build_annotation(
                    element,
                    annotation_type="arrow_highlight" if step_index == 1 else "highlight_only",
                    label_text=element.element_id,
                )

        risk = score_step(raw.get("action", ""), clean_desc)

        steps.append(Step(
            step_index=step_index,
            action=raw.get("action", ""),
            description=clean_desc if clean_desc else raw.get("description", ""),
            target_element_id=raw.get("target_element_id") or None,
            status="pending",
            annotation=annotation,
            risk_score=risk,
        ))

    if steps:
        steps[0].status = "active"

    detection_meta = {
        "route": "vision" if use_vision else "mock",
        "backend": "multimodal_llm" if use_vision else "template",
    }

    return ProcessResponse(
        task_id=str(uuid.uuid4()),
        success=True,
        intent=intent,
        ui_elements=elements,
        blueprint=Blueprint(name=summary, total_steps=len(steps), current_step=1, state="pending_confirm"),
        steps=steps,
        constraints=constraints,
        reference_resolution=[screen_w, screen_h],
        detection_meta=detection_meta,
    )


# ══════════════════════════════════════════════════════
#  重定位（OpenGuider 风格：直接看图找元素）
# ══════════════════════════════════════════════════════

_RELOCATE_VISION_PROMPT = """You are helping locate a UI element on a screenshot.

Look at the screenshot. Find the element that matches this step:
Step: {step_action}
Description: {step_description}

If the element IS visible, return:
{{"target_element_id": "found", "x": 500, "y": 300, "label": "element name", "confidence": 0.9}}

x and y are normalized 0-1000 coordinates.
If NOT visible, return:
{{"target_element_id": "", "x": 0, "y": 0, "label": "", "confidence": 0.0}}

Return ONLY valid JSON, no markdown."""


def relocate_step(
    step_action: str,
    step_description: str,
    image_base64: str,
) -> Tuple[Optional[str], Optional[Annotation], List[UIElement]]:
    """OpenGuider 风格重定位：截图发给 LLM 直接定位。"""
    elements: List[UIElement] = []

    if not settings.USE_REAL_LLM:
        return None, None, elements

    prompt = _RELOCATE_VISION_PROMPT.format(
        step_action=step_action,
        step_description=step_description,
    )

    result = call_deepseek(
        query=f"Find the element for: {step_description}",
        elements=None,
        image_base64=image_base64,
        system_prompt=prompt,
        temperature=0.1,
        max_tokens=1024,
        timeout=60,
    )

    if not result:
        return None, None, elements

    target_id = result.get("target_element_id", "")
    x, y = result.get("x", 0), result.get("y", 0)
    label = result.get("label", "")
    conf = result.get("confidence", 0.0)

    if not target_id or conf < 0.4:
        return None, None, elements

    # 归一化坐标 → 屏幕像素（默认 1920x1080）
    px, py = normalize_coordinate(float(x), float(y), 1920, 1080)
    half = 20
    bbox = [px - half, py - half, px + half, py + half]

    annotation = Annotation(
        type="arrow_highlight",
        highlight_bbox=bbox,
        arrow_to=[px, py],
        arrow_from=[px, max(0, py - 100)],
        label_position=[bbox[0], max(0, bbox[1] - 44)],
        label_text=label or step_action,
        confidence=conf,
    )

    return target_id, annotation, elements
