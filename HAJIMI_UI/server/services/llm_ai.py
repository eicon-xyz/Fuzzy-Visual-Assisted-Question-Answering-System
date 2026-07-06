"""
HAJIMI Demo AI 推理服务 —— 新模块统一路由层

本文件作为兼容入口，所有实现已迁移到：
- services/perception/     # 元素感知
- services/llm/            # LLM 调用
- services/planning/       # 规划与重规划
- services/intent/         # 意图分类

保留此文件是为了不破坏既有 import 路径。
"""

from typing import Dict, List, Optional, Tuple

from server.models.schemas import Intent, ProcessResponse, UIElement


def classify_intent(query: str) -> Tuple[str, str, float]:
    """意图分类入口"""
    from server.services.intent import classify_intent as new_classify_intent

    return new_classify_intent(query)


def detect_reference_type(query: str) -> str:
    """指代方式检测入口（关键词规则）"""
    q = query.lower()
    if any(k in q for k in ["这个", "那个", "这边", "那边"]):
        return "deictic"
    if any(k in q for k in ["左上角", "右上角", "左下角", "右下角", "中间"]):
        return "visual"
    if any(k in q for k in ["红色的", "蓝色的", "圆圆的", "齿轮"]):
        return "fuzzy"
    return "explicit"


def generate_steps(
    query: str, elements: Optional[List[UIElement]] = None
) -> List[dict]:
    """步骤生成入口 — 纯视觉 LLM"""
    from server.services.planning.router import process_query

    response = process_query(query, None)
    return [
        {
            "action": s.action,
            "description": s.instruction,
            "target_element_id": s.target_element_id,
        }
        for s in response.steps
    ]


def process_query(
    query: str,
    image_base64: Optional[str] = None,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> ProcessResponse:
    """核心流程入口 — 纯视觉 LLM 管道"""
    from server.services.planning.router import process_query as new_process_query

    return new_process_query(query, image_base64, screen_width, screen_height)


def call_deepseek(query: str, timeout: int = 30):
    """DeepSeek 调用入口"""
    from server.services.llm import call_deepseek as new_call_deepseek

    return new_call_deepseek(query, timeout=timeout)


def get_clarification_question(intent: Intent) -> str:
    """澄清问题生成入口"""
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
    return category_questions.get(intent.category, "能再具体描述一下您的需求吗？")


# ═══════════════════════════════════════════════════════════════════════════
# 图标匹配 — SoM 标注图 + LLM 识别
# ═══════════════════════════════════════════════════════════════════════════

IDENTIFY_SYSTEM_PROMPT = """You are a desktop icon identifier.
You see a screenshot with numbered bounding boxes drawn on desktop icons.
Your task: identify which box contains the target app icon.
Output ONLY valid JSON: {\"element_id\": \"~N\", \"confidence\": 0.95}
If the target is not visible, return {\"element_id\": null, \"confidence\": 0}."""


def identify_icon_from_som(
    som_image_base64: str, element_list_text: str, target_name: str
) -> dict:
    """
    Send SoM annotated image to LLM, ask it to identify which numbered box
    contains the target icon.

    Args:
        som_image_base64: OmniParser SoM annotated image (boxes with ~N labels)
        element_list_text: Serialized element list "{id}: center=[cx,cy]"
        target_name: e.g. "NetEase Cloud Music" or "Calculator"

    Returns:
        {"element_id": "~43", "confidence": 0.95} or {"element_id": None, "confidence": 0}
    """
    from server.services.llm.providers import call_llm, extract_json_object

    user_text = (
        f"Elements: {element_list_text}\n\n"
        f"Find the icon for: {target_name}. "
        f"Which numbered box contains it? Output JSON."
    )

    try:
        raw = call_llm(
            user_text=user_text,
            images=[{"base64Jpeg": som_image_base64, "label": "SoM"}],
            system_prompt=IDENTIFY_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=256,
            timeout=30,
        )
        return extract_json_object(raw)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"identify_icon_from_som failed: {e}")
        return {"element_id": None, "confidence": 0}


# ═══════════════════════════════════════════════════════════════════════════
# 步骤验证 — LLM 看图判断步骤是否完成
# ═══════════════════════════════════════════════════════════════════════════

VERIFY_SYSTEM_PROMPT = """你是一个桌面操作验证器。根据步骤描述和操作后的屏幕截图，判断该步骤是否已完成。

## 输出格式
严格返回 JSON：
{"status": "done", "confidence": 0.95, "rationale": "简要说明判断依据"}

status 取值：
- "done": 步骤明显完成了
- "not_done": 步骤没有完成，需要重试
- "uncertain": 无法从截图判断"""


def verify_step(image_base64: str, step: dict) -> Dict:
    """
    LLM 看图判断步骤是否完成。

    Args:
        image_base64: 操作后的新截图 base64
        step: 步骤 dict，含 description, action 等

    Returns:
        {"status": "done|not_done|uncertain", "confidence": float, "rationale": str}
    """
    from server.services.llm.providers import call_llm, extract_json_object

    description = step.get("description", "未知步骤")
    user_text = (
        f"步骤描述: {description}\n\n请根据操作后的屏幕截图，判断这个步骤是否已经完成。"
    )

    try:
        raw = call_llm(
            user_text=user_text,
            images=[{"base64Jpeg": image_base64, "label": "Screen"}],
            system_prompt=VERIFY_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=1024,
            timeout=60,
        )
        data = extract_json_object(raw)
        return {
            "status": data.get("status", "uncertain"),
            "confidence": float(data.get("confidence", 0.5)),
            "rationale": data.get("rationale", ""),
        }
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"verify_step failed: {e}")
        return {
            "status": "uncertain",
            "confidence": 0.3,
            "rationale": f"验证调用失败: {e}",
        }
