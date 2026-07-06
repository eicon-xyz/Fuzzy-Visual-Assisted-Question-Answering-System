"""Hybrid 融合定位单测。"""
from server.services.assist.hybrid_locate import score_candidate, try_hybrid_locate
from server.services.assist.types import AssistContext, CandidateElement


def _ctx(candidates, **bundle_extra) -> AssistContext:
    bundle = {
        "screen": {"scene_hint": "desktop"},
        "foreground": {"rect": [0, 0, 1920, 1080]},
        **bundle_extra,
    }
    return AssistContext(
        bundle=bundle,
        capture_size=[1920, 1080],
        candidates=candidates,
    )


class TestScoreCandidate:
    def test_exact_name_match(self):
        cand = CandidateElement(
            name="Google Chrome",
            bbox=[100, 200, 150, 250],
            confidence=0.85,
            source="desktop_shortcut",
            element_type="shortcut",
        )
        score = score_candidate(cand, ["Google Chrome"], [0, 0, 1920, 1080])
        assert score >= 0.7


class TestTryHybridLocate:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.setattr(
            "server.services.assist.hybrid_locate.ASSIST_ENABLED", False
        )
        ctx = _ctx(
            [
                CandidateElement(
                    name="Chrome",
                    bbox=[10, 10, 50, 50],
                    confidence=0.9,
                    source="uia",
                )
            ]
        )
        result = try_hybrid_locate(
            {"target": "Chrome", "description": "点击 Chrome"},
            image_b64="data:image/jpeg;base64,abc",
            user_query="打开 Chrome",
            ctx=ctx,
        )
        assert result.hit is False
        assert result.meta.get("skipped") == "assist_disabled"

    def test_hit_when_confidence_high(self, monkeypatch):
        monkeypatch.setattr(
            "server.services.assist.hybrid_locate.ASSIST_ENABLED", True
        )
        monkeypatch.setattr(
            "server.services.assist.hybrid_locate.ASSIST_HYBRID_MIN_CONFIDENCE", 0.72
        )
        ctx = _ctx(
            [
                CandidateElement(
                    name="Google Chrome",
                    bbox=[100, 200, 150, 250],
                    confidence=0.9,
                    source="desktop_shortcut",
                    element_type="shortcut",
                )
            ]
        )
        result = try_hybrid_locate(
            {"target": "Google Chrome", "description": "点击 Google Chrome 图标"},
            image_b64="data:image/jpeg;base64,abc",
            user_query="打开 Google Chrome",
            ctx=ctx,
        )
        assert result.hit is True
        assert result.annotation is not None
        assert result.source == "desktop_shortcut"

    def test_miss_when_no_candidates(self, monkeypatch):
        monkeypatch.setattr(
            "server.services.assist.hybrid_locate.ASSIST_ENABLED", True
        )
        ctx = _ctx([])
        result = try_hybrid_locate(
            {"target": "Chrome"},
            image_b64="data:image/jpeg;base64,abc",
            user_query="Chrome",
            ctx=ctx,
        )
        assert result.hit is False
