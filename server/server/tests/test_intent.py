"""
P1「SetFit 意图分类」单元测试（5 条核心用例）

运行方式：
    python -m pytest server/tests/test_intent.py -v
"""

from typing import Any, List, Tuple

import pytest

from server.services.intent import classify_intent, reset_classifier, setfit_classifier


@pytest.fixture(autouse=True)
def _reset_classifier_singleton() -> None:
    """每个用例结束后重置单例，避免状态污染。"""
    yield
    reset_classifier()


def _make_setfit_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """模拟 SetFit 无法加载：让 _load_model 不设置 self.model。"""
    monkeypatch.setattr(
        setfit_classifier.SetFitIntentClassifier, "_load_model", lambda self: None
    )


def _install_fake_setfit(
    monkeypatch: pytest.MonkeyPatch,
    predict_labels: List[str],
    proba_scores: List[List[float]],
) -> None:
    """注入伪造的 SetFit 模型，绕过模型目录与真实依赖检查。"""

    class FakeSetFitModel:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.labels = list(set(predict_labels))

        def __call__(self, texts: List[str]) -> List[str]:
            return self.predict(texts)

        def predict(self, texts: List[str]) -> List[str]:
            return [predict_labels[i % len(predict_labels)] for i in range(len(texts))]

        def predict_proba(self, texts: List[str]) -> List[List[float]]:
            return [proba_scores[i % len(proba_scores)] for i in range(len(texts))]

    def _fake_load_model(self: setfit_classifier.SetFitIntentClassifier) -> None:
        self.model = FakeSetFitModel()
        self.labels = list(self.model.labels)

    monkeypatch.setattr(
        setfit_classifier.SetFitIntentClassifier, "_load_model", _fake_load_model
    )


def test_keywords_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """1. SetFit 不可用时，走 keywords fallback，安装类查询返回固定摘要。"""
    _make_setfit_unavailable(monkeypatch)

    category, summary, confidence = classify_intent("怎么安装微信")

    assert category == "operation_guide"
    assert summary == "安装软件"
    assert confidence == 0.92


def test_classify_all_nine_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    """2. keywords 路径能覆盖全部 9 类意图，每类取 1 条样本验证。"""
    _make_setfit_unavailable(monkeypatch)

    cases: List[Tuple[str, str, Tuple[str, str, float]]] = [
        ("operation_guide", "怎么安装微信", ("operation_guide", "安装软件", 0.92)),
        (
            "element_cognition",
            "这个图标是什么意思",
            ("element_cognition", "元素认知", 0.86),
        ),
        (
            "error_diagnosis",
            "提示网络错误怎么办",
            ("error_diagnosis", "错误诊断", 0.84),
        ),
        ("ui_navigation", "亮度调节在哪个菜单", ("ui_navigation", "界面导航", 0.83)),
        (
            "content_cognition",
            "总结一下这段文字",
            ("content_cognition", "内容认知", 0.83),
        ),
        ("file_management", "怎么查找桌面文件", ("file_management", "文件管理", 0.82)),
        (
            "proactive_alert",
            "提醒我下午三点开会",
            ("proactive_alert", "主动提醒", 0.82),
        ),
        (
            "tutorial_generation",
            "录制操作过程做成视频",
            ("tutorial_generation", "生成教程", 0.82),
        ),
        ("emotion_comfort", "我不会用这个软件", ("emotion_comfort", "情绪安抚", 0.80)),
    ]

    for expected_category, query, expected in cases:
        category, summary, confidence = classify_intent(query)
        assert (category, summary, confidence) == expected, (
            f"类别 {expected_category} 的分类结果不匹配: "
            f"got ({category}, {summary}, {confidence})"
        )


def test_setfit_overrides_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """3. mock SetFitModel.predict 返回不同类别时，优先使用 SetFit 结果。"""
    # 安装微信走 keywords 会返回 operation_guide；这里让 SetFit 强行判为 element_cognition
    _install_fake_setfit(
        monkeypatch,
        predict_labels=["element_cognition"],
        proba_scores=[[0.1, 0.9]],
    )

    category, summary, confidence = classify_intent("怎么安装微信")

    assert category == "element_cognition"
    assert summary == "元素认知"
    assert confidence == 0.9


def test_low_confidence_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """4. mock predict_proba 置信度 0.3，低于阈值 0.6，回退到 keywords。"""
    _install_fake_setfit(
        monkeypatch,
        predict_labels=["element_cognition"],
        proba_scores=[[0.1, 0.3, 0.2]],
    )

    category, summary, confidence = classify_intent("怎么安装微信")

    assert category == "operation_guide"
    assert summary == "安装软件"
    assert confidence == 0.92


def test_reset_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """5. reset_classifier() 后重新实例化，单例对象被刷新。"""
    _make_setfit_unavailable(monkeypatch)

    # 先触发一次实例化
    classify_intent("怎么安装微信")
    first_instance = setfit_classifier._classifier
    assert first_instance is not None

    # 重置并再次调用，应得到新的实例
    reset_classifier()
    classify_intent("怎么安装微信")
    second_instance = setfit_classifier._classifier

    assert second_instance is not None
    assert second_instance is not first_instance
