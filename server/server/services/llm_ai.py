"""
HAJIMI Demo AI 推理服务 —— 新模块统一路由层

本文件作为兼容入口，所有实现已迁移到：
- services/perception/     # 元素感知
- services/llm/            # LLM 调用
- services/planning/       # 规划与重规划
- services/intent/         # 意图分类

保留此文件是为了不破坏既有 import 路径。
"""
from typing import List, Tuple, Optional

from server.models.schemas import UIElement, ProcessResponse, Intent


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


def generate_steps(query: str, elements: Optional[List[UIElement]] = None) -> List[dict]:
    """步骤生成入口"""
    from server.services.planning import generate_steps as new_generate_steps
    steps, _ = new_generate_steps(query, elements)
    return steps


def process_query(query: str, image_base64: Optional[str] = None) -> ProcessResponse:
    """核心流程入口"""
    from server.services.planning import process_query as new_process_query
    return new_process_query(query, image_base64)


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
    return category_questions.get(
        intent.category, "能再具体描述一下您的需求吗？"
    )
