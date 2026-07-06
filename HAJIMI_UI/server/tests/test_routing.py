"""Tests for OpenGuider-style routing, vision point parser, and latency meta."""
import pytest

from server.config import settings
from server.services.latency_tracker import LatencyBreakdown, PhaseTimer
from server.services.planning.route_selector import (
    route_skips_omniparser,
    route_uses_per_step_locate,
    select_route,
)
from server.services.plugins.browser_router import generate_browser_plan, is_browser_task
from server.services.vision.point_parser import (
    build_annotation_from_point,
    normalized_to_pixel,
    parse_point_tag,
)


class TestPointParser:
    def test_parse_point_tag_normalized(self):
        text = "Click here [POINT:850,450:Submit Button]"
        clean, coord, label = parse_point_tag(text)
        assert "Submit" in clean or "Click" in clean
        assert coord == {"x": 850.0, "y": 450.0}
        assert label == "Submit Button"

    def test_normalized_to_pixel(self):
        px, py = normalized_to_pixel(500, 500, 1920, 1080)
        assert px == 960
        assert py == 540

    def test_build_annotation(self):
        ann = build_annotation_from_point(500, 500, 1000, 800, label="Go")
        assert ann.highlight_bbox is not None
        assert ann.label_text == "Go"


class TestRouteSelector:
    def test_l2_screenshot_skip(self, monkeypatch):
        from server.services.planning.complexity_router import generate_l2_steps

        monkeypatch.setattr(settings, "ROUTING_MODE", "auto")
        l2 = generate_l2_steps("怎么截图", None)
        route = select_route("怎么截图", has_image=True, l2_steps=l2)
        assert route == "L2"

    def test_l4_auto_with_image(self, monkeypatch):
        monkeypatch.setattr(settings, "ROUTING_MODE", "auto")
        monkeypatch.setattr(settings, "BROWSER_PLUGIN_ENABLED", True)
        route = select_route("帮我在 Word 里设置页边距", has_image=True)
        assert route == "L4"

    def test_precision_uses_l3(self, monkeypatch):
        monkeypatch.setattr(settings, "ROUTING_MODE", "precision")
        route = select_route("帮我在 Word 里设置页边距", has_image=True)
        assert route == "L3"

    def test_balanced_deferred(self, monkeypatch):
        monkeypatch.setattr(settings, "ROUTING_MODE", "balanced")
        route = select_route("帮我在 Word 里设置页边距", has_image=True)
        assert route == "L3_DEFERRED"

    def test_browser_route(self, monkeypatch):
        monkeypatch.setattr(settings, "BROWSER_PLUGIN_ENABLED", True)
        assert is_browser_task("在浏览器打开 https://example.com")
        route = select_route("在浏览器打开 https://example.com", has_image=True)
        assert route == "BROWSER"

    def test_route_flags(self):
        assert route_skips_omniparser("L4")
        assert route_uses_per_step_locate("L3_DEFERRED")
        assert not route_skips_omniparser("L3")


class TestBrowserPlugin:
    def test_generate_browser_plan(self):
        steps, constraints, meta = generate_browser_plan("搜索 OpenAI 文档")
        assert len(steps) >= 2
        assert steps[0]["interaction"] == "browser"
        assert constraints.get("browser_automation") is True
        assert meta["browser_plugin"] is True


class TestLatencyBreakdown:
    def test_to_meta(self):
        lb = LatencyBreakdown(route="L4")
        lb.mark_parse(0, skipped=True)
        lb.mark_plan(120)
        lb.mark_locate(800)
        lb.total_ms = 950
        meta = lb.to_meta()
        assert meta["route"] == "L4"
        assert meta["parse_skipped"] is True
        assert meta["latency_breakdown"]["plan_ms"] == 120
        assert meta["latency_breakdown"]["locate_ms"] == 800

    def test_phase_timer(self):
        with PhaseTimer() as t:
            pass
        assert t.ms >= 0


class TestProcessQueryRouting:
    def test_process_l4_meta_without_omniparser(self, monkeypatch):
        from server.services.llm_ai import process_query

        settings.USE_REAL_LLM = False
        monkeypatch.setattr(settings, "ROUTING_MODE", "fast")
        monkeypatch.setattr(
            "server.services.planning.router.run_l4_process",
            lambda query, **kw: __import__(
                "server.services.l4.types", fromlist=["L4ProcessResult"]
            ).L4ProcessResult(
                raw_steps=[
                    {"action": "a", "description": "d", "target_element_id": "", "interaction": "screen"}
                ],
                constraints=None,
                llm_meta={"llm_called": True, "route": "L4", "locator_first": {}},
                reference_resolution=[1920, 1080],
                first_step_annotation=None,
            ),
        )
        resp = process_query("复杂任务需要多步", "data:image/png;base64,abc")
        assert resp.success
        assert resp.detection_meta.get("route") == "L4"
        assert resp.detection_meta.get("omniparser_skipped") is True
        assert "latency_breakdown" in (resp.detection_meta or {})
