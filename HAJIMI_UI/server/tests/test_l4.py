"""L4 Vision 快路径单元测试。"""
import pytest

from server.services.l4.calibration import (
    finalize_l4_annotation,
    scale_annotation_to_capture,
)
from server.services.l4.point_parser import (
    build_annotation_from_point,
    normalized_to_pixel,
    parse_point_tag,
)
from server.services.l4.types import L4ScreenContext
from server.models.schemas import Annotation


class TestL4PointParser:
    def test_parse_point_none(self):
        _, coord, _ = parse_point_tag("无法定位 [POINT:none]")
        assert coord is None

    def test_normalized_1000_space(self):
        px, py = normalized_to_pixel(500, 500, 1000, 800)
        assert px == 500
        assert py == 400


class TestL4Calibration:
    def test_scale_upload_to_capture(self):
        ann = build_annotation_from_point(500, 500, 720, 405, label="Go")
        scaled = scale_annotation_to_capture(ann, (720, 405), (1920, 1080))
        assert scaled.highlight_bbox is not None
        cx = (scaled.highlight_bbox[0] + scaled.highlight_bbox[2]) // 2
        assert 900 < cx < 1000

    def test_finalize_with_capture_size(self):
        ctx = L4ScreenContext(capture_size=[1920, 1080])
        ann = build_annotation_from_point(500, 500, 720, 405)
        out, ref = finalize_l4_annotation(ann, ctx, 720, 405)
        assert ref == [1920, 1080]
        assert out.highlight_bbox is not None


class TestL4StepUtils:
    def test_hotkey_skips_locate(self):
        from server.services.l4.step_utils import step_needs_locate

        assert not step_needs_locate(
            {"action": "hotkey", "description": "按 Win 键打开开始菜单"}
        )

    def test_wait_is_keyboard(self):
        from server.services.l4.step_utils import apply_step_interaction, step_needs_locate

        step = apply_step_interaction(
            {"action": "wait", "description": "等待页面加载完成"}
        )
        assert step.get("interaction") == "keyboard"
        assert not step_needs_locate(step)

    def test_deferred_keyword_on_screen_action(self):
        from server.services.l4.step_utils import apply_step_interaction

        step = apply_step_interaction(
            {"action": "click", "description": "等待加载完成后点击保存"}
        )
        assert step.get("locate_deferred") is True

    def test_click_needs_locate(self):
        from server.services.l4.step_utils import step_needs_locate

        assert step_needs_locate({"action": "click", "description": "点击保存按钮"})


class TestL4Orchestrator:
    def test_run_l4_process_locates_first_screen_step_after_hotkey(self, monkeypatch):
        from server.services.l4 import run_l4_process

        locate_called = {"indices": []}

        def _fake_locate(step, *a, **k):
            locate_called["indices"].append(step.get("description"))
            return __import__(
                "server.services.l4.types", fromlist=["L4LocateResult"]
            ).L4LocateResult(
                annotation=build_annotation_from_point(500, 500, 720, 405),
                reference_resolution=[1920, 1080],
                llm_meta={},
            )

        monkeypatch.setattr(
            "server.services.l4.orchestrator.plan_l4_steps",
            lambda *a, **k: (
                [
                    {
                        "step_number": 1,
                        "action": "hotkey",
                        "description": "按 Win 键",
                    },
                    {
                        "step_number": 2,
                        "action": "click",
                        "description": "点按钮",
                    },
                ],
                {"model": "mock"},
            ),
        )
        monkeypatch.setattr(
            "server.services.l4.orchestrator.locate_l4_step", _fake_locate
        )
        result = run_l4_process(
            "打开开始菜单",
            image_b64="data:image/png;base64,abc",
            capture_size=[1920, 1080],
            upload_size=[720, 405],
        )
        assert len(locate_called["indices"]) == 0
        assert result.first_step_annotation is None
        assert "located_step_index" not in (result.llm_meta.get("locator_first") or {})
        assert result.raw_steps[0].get("interaction") == "keyboard"

    def test_run_l4_process_mocked(self, monkeypatch):
        from server.services.l4 import run_l4_process

        monkeypatch.setattr(
            "server.services.l4.orchestrator.plan_l4_steps",
            lambda *a, **k: (
                [{"step_number": 1, "action": "click", "target": "按钮", "description": "点按钮"}],
                {"model": "mock"},
            ),
        )
        monkeypatch.setattr(
            "server.services.l4.orchestrator.locate_l4_step",
            lambda *a, **k: __import__(
                "server.services.l4.types", fromlist=["L4LocateResult"]
            ).L4LocateResult(
                annotation=build_annotation_from_point(500, 500, 720, 405),
                reference_resolution=[1920, 1080],
                llm_meta={"latency_ms": 100},
            ),
        )
        result = run_l4_process(
            "点击保存",
            image_b64="data:image/png;base64,abc",
            capture_size=[1920, 1080],
            upload_size=[720, 405],
        )
        assert len(result.raw_steps) == 1
        assert result.raw_steps[0].get("interaction") == "screen"
        assert result.first_step_annotation is not None
        assert result.reference_resolution == [1920, 1080]
