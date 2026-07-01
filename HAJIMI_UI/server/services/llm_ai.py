"""
HAJIMI Demo AI 推理服务
Replicate OmniParser 真实检测 + DeepSeek 步骤/元素绑定
"""
import json
import re
import uuid
import httpx
from typing import List, Tuple, Optional, Dict, Any

from server.config import settings
from server.models.schemas import (
    UIElement,
    Step,
    Blueprint,
    Intent,
    ProcessResponse,
    Annotation,
    InspectResponse,
)
from server.services.image_utils import decode_image
from server.services import ui_detector, som_renderer
from server.services.ui_detector import DetectorError


# ────────────────────────── Mock 场景数据 ──────────────────────────

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


# ────────────────────────── 意图分类（简单规则）──────────────────────────


def classify_intent(query: str) -> Tuple[str, str, float]:
    """
    基于关键词的意图分类（Demo 阶段简化）
    返回: (category, summary, confidence)
    """
    q = query.lower()

    if any(k in q for k in ["安装", "下载", "怎么装", "如何装"]):
        return "operation_guide", "安装软件", 0.92
    if any(k in q for k in ["截图", "截屏", "保存图片"]):
        return "operation_guide", "屏幕截图", 0.90
    if any(k in q for k in ["保存", "另存为", "存文件"]):
        return "operation_guide", "保存文件", 0.88
    if any(k in q for k in ["打开", "启动", "运行"]):
        return "operation_guide", "打开应用", 0.85
    if any(k in q for k in ["设置", "配置", "怎么调"]):
        return "ui_navigation", "查找设置", 0.82

    return "operation_guide", "通用操作指引", 0.75


def detect_reference_type(query: str) -> str:
    """检测指代方式（简化）"""
    q = query.lower()
    if any(k in q for k in ["这个", "那个", "这边", "那边"]):
        return "deictic"
    if any(k in q for k in ["左上角", "右上角", "左下角", "右下角", "中间"]):
        return "visual"
    if any(k in q for k in ["红色的", "蓝色的", "圆圆的", "齿轮"]):
        return "fuzzy"
    return "explicit"


def choose_scenario(query: str) -> str:
    """根据查询选择场景"""
    q = query.lower()
    if any(k in q for k in ["微信", "qq", "软件", "下载", "安装"]):
        return "wechat"
    if any(k in q for k in ["截图", "截屏", "snip"]):
        return "screenshot"
    return "default"


def build_annotation(
    element: UIElement, annotation_type: str, label_text: str
) -> Annotation:
    """为 UI 元素生成标注"""
    x1, y1, x2, y2 = element.bbox
    cx, cy = element.center or [(x1 + x2) // 2, (y1 + y2) // 2]

    # 箭头从屏幕左侧或上方边缘指向元素中心
    arrow_from = [max(0, cx - 150), max(0, cy - 100)]
    arrow_to = [cx, cy]

    # 标签放在元素上方
    label_x = x1
    label_y = max(0, y1 - 44)

    return Annotation(
        type=annotation_type,
        arrow_from=arrow_from,
        arrow_to=arrow_to,
        highlight_bbox=element.bbox,
        label_position=[label_x, label_y],
        label_text=label_text,
    )


# ────────────────────────── LLM 调用 ──────────────────────────


SYSTEM_PROMPT = """你是一个桌面操作指引助手。请根据用户的提问，生成清晰、安全的分步操作指引。
请严格按以下 JSON 格式返回，不要返回任何其他内容：

{
  "steps": [
    {
      "action": "简短动作",
      "description": "给用户看的详细说明"
    }
  ]
}

要求：
1. 只输出 JSON，不要 markdown 代码块
2. 步骤控制在 2-5 步
3. 每一步必须是用户可手动执行的操作
4. 不要自动替用户点击或操作
"""


def call_deepseek(query: str, timeout: int = 30) -> Optional[List[dict]]:
    """
    调用 DeepSeek API 生成操作步骤
    返回步骤列表，失败返回 None
    """
    if not settings.DEEPSEEK_API_KEY:
        return None

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1000,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return parse_llm_steps(content)
    except Exception as e:
        print(f"[LLM Error] {type(e).__name__}: {e}")
        return None


def parse_llm_steps(content: str) -> Optional[List[dict]]:
    """从 LLM 返回内容中提取步骤 JSON"""
    # 尝试直接解析
    try:
        data = json.loads(content)
        if "steps" in data:
            return data["steps"]
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if code_block:
        try:
            data = json.loads(code_block.group(1))
            if "steps" in data:
                return data["steps"]
        except json.JSONDecodeError:
            pass

    # 尝试查找第一个 JSON 对象
    json_match = re.search(r"\{[\s\S]*\"steps\"[\s\S]*\}", content)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if "steps" in data:
                return data["steps"]
        except json.JSONDecodeError:
            pass

    return None


# ────────────────────────── 主流程 ──────────────────────────


def generate_steps(query: str) -> List[dict]:
    """
    生成操作步骤，优先使用 LLM，失败则 fallback 到 mock
    """
    if settings.USE_REAL_LLM:
        llm_steps = call_deepseek(query)
        if llm_steps:
            return llm_steps

    # Fallback: 根据场景返回 mock 步骤
    scenario = choose_scenario(query)
    fallbacks = {
        "wechat": [
            {"action": "打开浏览器", "description": "找到桌面上的浏览器图标，双击打开。"},
            {"action": "访问微信官网", "description": "在地址栏输入 weixin.qq.com 并回车。"},
            {"action": "点击下载按钮", "description": "在官网首页找到「下载」按钮并点击。"},
            {"action": "运行安装程序", "description": "下载完成后，双击安装包按提示完成安装。"},
        ],
        "screenshot": [
            {"action": "打开截图工具", "description": "按下 Win + Shift + S 打开系统截图工具。"},
            {"action": "选择截图区域", "description": "拖动鼠标选择要截取的区域。"},
            {"action": "保存截图", "description": "截图完成后，点击通知中的预览并保存。"},
        ],
        "default": [
            {"action": "观察当前界面", "description": "仔细查看屏幕上的可点击元素。"},
            {"action": "按提示操作", "description": "根据系统指引逐步完成目标。"},
        ],
    }
    return fallbacks.get(scenario, fallbacks["default"])


SYSTEM_PROMPT_WITH_ELEMENTS = """你是一个桌面操作指引助手。屏幕截图已解析为带编号的 UI 元素（~1, ~2, ...）。
请根据用户问题和元素列表，生成操作步骤，并为每一步指定 target_element_id。

严格按以下 JSON 格式返回，不要 markdown 代码块：

{
  "steps": [
    {
      "action": "简短动作",
      "description": "给用户看的详细说明",
      "target_element_id": "~1"
    }
  ]
}

要求：
1. target_element_id 必须来自提供的元素列表
2. 步骤 2-5 步，每步用户可手动执行
3. 不要自动替用户点击
"""


def _format_elements_for_llm(elements: List[UIElement]) -> str:
    lines = []
    for el in elements[:40]:
        cx, cy = (el.center or [0, 0])
        text = (el.text or "").replace("\n", " ")[:40]
        lines.append(
            f"{el.element_id} [{el.element_type}] \"{text}\" center=({cx},{cy}) conf={el.confidence:.2f}"
        )
    return "\n".join(lines)


def call_deepseek_with_elements(
    query: str, elements: List[UIElement], timeout: int = 30
) -> Optional[List[dict]]:
    if not settings.DEEPSEEK_API_KEY or not elements:
        return None

    user_content = (
        f"用户问题：{query}\n\n"
        f"屏幕元素列表：\n{_format_elements_for_llm(elements)}\n\n"
        "请为每一步选择最匹配的 target_element_id。"
    )

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT_WITH_ELEMENTS},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1200,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return parse_llm_steps(content)
    except Exception as e:
        print(f"[LLM Error] {type(e).__name__}: {e}")
        return None


def lookup_element(elements: List[UIElement], element_id: str) -> Optional[UIElement]:
    for el in elements:
        if el.element_id == element_id:
            return el
    return None


def pick_fallback_element(raw: dict, elements: List[UIElement], index: int) -> UIElement:
    eid = raw.get("target_element_id")
    if eid:
        found = lookup_element(elements, eid)
        if found:
            return found

    desc = (raw.get("description") or raw.get("action") or "").lower()
    if desc:
        for el in elements:
            if el.text and el.text.lower() in desc:
                return el
            if el.text and desc in el.text.lower():
                return el

    if elements:
        return elements[min(index, len(elements) - 1)]
    raise ValueError("no elements available")


def run_detection(image_b64: str):
    pil, w, h = decode_image(image_b64)
    detection = ui_detector.detect(pil)
    annotated = som_renderer.render_base64(pil, detection.elements)
    meta = {
        "latency_ms": detection.latency_ms,
        "element_count": len(detection.elements),
        "backend": detection.backend,
    }
    return pil, w, h, detection, annotated, meta


def inspect_image(image_b64: str) -> InspectResponse:
    try:
        pil, w, h, detection, annotated, meta = run_detection(image_b64)
    except (ValueError, DetectorError) as exc:
        raise exc

    if not detection.elements:
        raise ValueError("NO_ELEMENTS_DETECTED")

    return InspectResponse(
        success=True,
        ui_elements=detection.elements,
        annotated_image=annotated,
        reference_resolution=[w, h],
        detection_meta=meta,
    )


def process_query(query: str, image_b64: Optional[str] = None) -> ProcessResponse:
    """
    处理用户查询：真实截图检测 + LLM 步骤与元素绑定
    """
    if not image_b64 and settings.REQUIRE_IMAGE:
        raise ValueError("MISSING_IMAGE")

    elements: List[UIElement] = []
    annotated_b64: Optional[str] = None
    ref_res: Optional[List[int]] = None
    detection_meta: Optional[Dict[str, Any]] = None

    if image_b64:
        pil, w, h, detection, annotated_b64, detection_meta = run_detection(image_b64)
        elements = detection.elements
        ref_res = [w, h]
        if not elements:
            if settings.ALLOW_DETECTOR_FALLBACK:
                print("[process] NO_ELEMENTS_DETECTED, using scenario fallback")
                scenario = choose_scenario(query)
                elements = SCENARIO_ELEMENTS[scenario].copy()
            else:
                raise ValueError("NO_ELEMENTS_DETECTED")
    else:
        scenario = choose_scenario(query)
        elements = SCENARIO_ELEMENTS[scenario].copy()

    category, summary, confidence = classify_intent(query)
    reference_type = detect_reference_type(query)
    intent = Intent(
        category=category,
        summary=summary,
        reference_type=reference_type,
        confidence=confidence,
        needs_clarification=confidence < 0.80,
    )

    raw_steps = None
    if settings.USE_REAL_LLM and elements:
        raw_steps = call_deepseek_with_elements(query, elements)
    if not raw_steps:
        raw_steps = generate_steps(query)

    steps: List[Step] = []
    for i, raw in enumerate(raw_steps):
        step_index = i + 1
        raw_eid = raw.get("target_element_id")
        matched = lookup_element(elements, raw_eid) if raw_eid else None
        locate_deferred = matched is None
        if matched:
            element = matched
        else:
            element = pick_fallback_element(raw, elements, i)
        annotation = None if locate_deferred else build_annotation(
            element,
            annotation_type="arrow_highlight" if step_index == 1 else "highlight_only",
            label_text=element.element_id,
        )
        prepare_hint = raw.get("description", "") if locate_deferred else None
        steps.append(
            Step(
                step_index=step_index,
                action=raw["action"],
                description=raw["description"],
                target_element_id=element.element_id if not locate_deferred else raw_eid,
                status="pending",
                annotation=annotation,
                locate_deferred=locate_deferred,
                prepare_hint=prepare_hint,
            )
        )

    if steps:
        steps[0].status = "active"

    blueprint = Blueprint(
        name=summary,
        total_steps=len(steps),
        current_step=1,
        state="executing",
    )

    return ProcessResponse(
        task_id=str(uuid.uuid4()),
        success=True,
        intent=intent,
        ui_elements=elements,
        annotated_image=annotated_b64,
        blueprint=blueprint,
        steps=steps,
        reference_resolution=ref_res,
        detection_meta=detection_meta,
    )


def relocate_step_on_screen(
    state_query: str,
    step: Step,
    image_b64: str,
) -> Tuple[List[UIElement], Annotation, List[int], Dict[str, Any]]:
    """用户完成手动操作后，对新截图检测并绑定当前步骤目标元素。"""
    pil, w, h = decode_image(image_b64)
    detection = ui_detector.detect(pil)
    elements = detection.elements
    if not elements:
        raise ValueError("NO_ELEMENTS_DETECTED")

    raw = {
        "action": step.action,
        "description": step.description,
        "target_element_id": step.target_element_id,
    }
    picked = None
    if settings.USE_REAL_LLM:
        llm_steps = call_deepseek_with_elements(
            f"{state_query}\n当前只需定位一步：{step.description}", elements
        )
        if llm_steps:
            raw["target_element_id"] = llm_steps[0].get("target_element_id")
            picked = lookup_element(elements, raw.get("target_element_id") or "")
    if not picked:
        picked = pick_fallback_element(raw, elements, 0)

    annotation = build_annotation(
        picked,
        annotation_type="arrow_highlight",
        label_text=picked.element_id,
    )
    meta = {
        "latency_ms": detection.latency_ms,
        "element_count": len(elements),
        "backend": detection.backend,
    }
    return elements, annotation, [w, h], meta


def get_clarification_question(intent: Intent) -> str:
    """生成澄清问题"""
    category_questions = {
        "operation_guide": "您是想执行某个具体操作，还是想了解某个功能的位置？",
        "element_cognition": "您想了解的是哪个图标或按钮的含义？",
        "error_diagnosis": "您遇到了什么错误提示？",
        "ui_navigation": "您要找的功能大概在哪个菜单里？",
        "content_cognition": "您是想总结、翻译还是提取当前内容？",
        "file_management": "您是想查找、移动还是删除文件？",
        "proactive_alert": "您希望收到哪类提醒？",
        "tutorial_generation": "您想保存为文字教程还是视频步骤？",
        "emotion_comfort": "请告诉我您卡在了哪一步？",
    }
    return category_questions.get(
        intent.category, "能再具体描述一下您的需求吗？"
    )
