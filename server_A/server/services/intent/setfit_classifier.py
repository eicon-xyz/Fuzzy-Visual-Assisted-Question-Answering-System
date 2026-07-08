"""
SetFit 意图分类推理模块

特性:
    - 加载 server/config.py 中 INTENT_MODEL_PATH 指定的 SetFit 模型
    - 模型不存在或加载失败时，自动回退到关键词规则
    - SetFit 预测置信度低于阈值时，同样回退到关键词规则
"""

import os
from pathlib import Path
from typing import Any, Optional, Tuple

from server.config import settings

# 在中国大陆默认使用 Hugging Face 镜像，可通过环境变量覆盖
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# SetFit 预测置信度阈值，低于该值视为不确定，触发 keywords fallback
CONFIDENCE_THRESHOLD = 0.6

# 意图类别 -> 默认摘要
CATEGORY_SUMMARIES: dict[str, str] = {
    "operation_guide": "通用操作指引",
    "element_cognition": "元素认知",
    "error_diagnosis": "错误诊断",
    "ui_navigation": "界面导航",
    "content_cognition": "内容认知",
    "file_management": "文件管理",
    "proactive_alert": "主动提醒",
    "tutorial_generation": "生成教程",
    "emotion_comfort": "情绪安抚",
}


def _keywords_classify(query: str) -> Tuple[str, str, float]:
    """
    基于关键词的意图分类 fallback。

    对 operation_guide 的前几条规则与旧版 _legacy_classify_intent 保持一致，
    确保 SetFit 模型不可用时 fallback 行为不变。
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

    if any(
        k in q for k in ["这个图标", "那个按钮", "是什么意思", "有什么用", "代表什么"]
    ):
        return "element_cognition", "元素认知", 0.86
    if any(
        k in q for k in ["错误", "报错", "失败", "无法", "不能", "出错", "闪退", "蓝屏"]
    ):
        return "error_diagnosis", "错误诊断", 0.84
    if any(k in q for k in ["在哪里", "在哪", "怎么找", "哪个菜单", "位置", "界面"]):
        return "ui_navigation", "界面导航", 0.83
    if any(k in q for k in ["总结", "翻译", "提取", "内容", "文字", "复制", "识别"]):
        return "content_cognition", "内容认知", 0.83
    if any(
        k in q
        for k in ["文件", "文件夹", "移动", "删除", "查找", "重命名", "压缩", "解压"]
    ):
        return "file_management", "文件管理", 0.82
    if any(k in q for k in ["提醒", "通知", "闹钟", "定时", "叫我", "到时"]):
        return "proactive_alert", "主动提醒", 0.82
    if any(
        k in q for k in ["教程", "步骤", "录制成", "做成视频", "使用说明", "培训材料"]
    ):
        return "tutorial_generation", "生成教程", 0.82
    if any(
        k in q
        for k in ["不会", "搞不定", "着急", "卡住", "帮帮我", "沮丧", "担心", "耐心"]
    ):
        return "emotion_comfort", "情绪安抚", 0.80

    return "operation_guide", "通用操作指引", 0.75


class SetFitIntentClassifier:
    """
    SetFit 意图分类器封装。

    模型不可用时自动回退到关键词规则，保证服务可用性。
    """

    def __init__(self, model_path: Optional[str] = None) -> None:
        self.model_path = model_path or settings.INTENT_MODEL_PATH
        self.model: Optional[Any] = None
        self.labels: list[str] = []
        self._load_model()

    def _load_model(self) -> None:
        """尝试加载本地 SetFit 模型。"""
        try:
            # 延迟导入：未安装 setfit 时直接走 fallback
            from setfit import SetFitModel
        except Exception as exc:  # pragma: no cover - 环境缺失依赖
            print(f"[Intent] setfit not available: {exc}")
            return

        model_dir = Path(self.model_path)
        if not model_dir.exists():
            return

        try:
            self.model = SetFitModel.from_pretrained(str(model_dir))
            self.labels = list(self.model.labels) if self.model.labels else []
        except Exception as exc:
            print(f"[Intent] Failed to load SetFit model: {exc}")
            self.model = None

    def classify(self, query: str) -> Tuple[str, str, float]:
        """
        对输入查询进行意图分类。

        Returns:
            (category, summary, confidence)
        """
        if self.model is None:
            return _keywords_classify(query)

        try:
            predictions = self.model([query])
            category = str(predictions[0])

            confidence = 0.85
            if hasattr(self.model, "predict_proba"):
                proba = self.model.predict_proba([query])
                # proba 可能是 list[list[float]] 或 ndarray
                if hasattr(proba, "tolist"):
                    proba_list = proba.tolist()
                else:
                    proba_list = list(proba)
                confidence = float(max(proba_list[0]))

            if confidence < CONFIDENCE_THRESHOLD:
                return _keywords_classify(query)

            # 优先使用 keywords fallback 给出的业务摘要，保持与旧逻辑一致
            fallback = _keywords_classify(query)
            if fallback[0] == category:
                summary = fallback[1]
            else:
                summary = CATEGORY_SUMMARIES.get(category, "通用意图")

            return category, summary, round(confidence, 4)
        except Exception as exc:
            print(f"[Intent] SetFit inference failed: {exc}")
            return _keywords_classify(query)


_classifier: Optional[SetFitIntentClassifier] = None


def classify_intent(query: str) -> Tuple[str, str, float]:
    """
    意图分类入口（单例）。

    Args:
        query: 用户原始查询

    Returns:
        (category, summary, confidence)
    """
    global _classifier
    if _classifier is None:
        _classifier = SetFitIntentClassifier()
    return _classifier.classify(query)


def reset_classifier() -> None:
    """重置单例，主要用于测试。"""
    global _classifier
    _classifier = None
