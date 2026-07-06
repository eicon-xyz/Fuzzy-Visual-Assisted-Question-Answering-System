"""Prepare 引导场景解析单测。"""
from core.prepare_guidance import (
    PrepareScene,
    resolve_prepare_scene,
)


def _step(**kwargs):
    base = {
        "action": "click",
        "description": "点击 Google Chrome 桌面图标",
        "target": "Google Chrome",
    }
    base.update(kwargs)
    return base


class TestResolvePrepareScene:
    def test_first_failure_primary_is_relocate(self):
        scene = resolve_prepare_scene(_step(), relocate_fail_count=0)
        assert scene.scene_id == "locate_failed_first"
        assert scene.primary_preset_id == "relocate"
        assert "Google Chrome" in scene.body

    def test_retry_primary_is_advance(self):
        scene = resolve_prepare_scene(_step(), relocate_fail_count=1)
        assert scene.scene_id == "locate_failed_retry"
        assert scene.primary_preset_id == "advance"

    def test_multi_step_stuck_for_desktop_retry(self):
        scene = resolve_prepare_scene(
            _step(description="点击桌面回收站图标"),
            relocate_fail_count=1,
            current_step_index=0,
            total_steps=2,
        )
        assert scene.scene_id == "locate_failed_retry"
        assert scene.primary_preset_id == "advance"

    def test_deferred_manual(self):
        scene = resolve_prepare_scene(
            _step(locate_deferred=True, prepare_hint="等待桌面加载完成"),
            relocate_fail_count=0,
        )
        assert scene.scene_id == "deferred_manual"
        assert scene.primary_preset_id == "relocate"
        assert "等待桌面" in scene.body

    def test_scene_to_dict_roundtrip(self):
        scene = resolve_prepare_scene(_step(), relocate_fail_count=0)
        restored = PrepareScene.from_dict(scene.to_dict())
        assert restored.scene_id == scene.scene_id
        assert restored.primary_preset_id == scene.primary_preset_id
        assert len(restored.presets) == len(scene.presets)

    def test_secondary_presets_exclude_primary(self):
        scene = resolve_prepare_scene(_step(), relocate_fail_count=0)
        secondary_ids = {p.id for p in scene.secondary_presets()}
        assert "relocate" not in secondary_ids
        assert "advance" in secondary_ids

    def test_browser_desktop_mismatch(self):
        scene = resolve_prepare_scene(
            _step(description="点击桌面 Google Chrome 图标"),
            relocate_fail_count=0,
            scene_hint="browser",
            assist_bundle={
                "foreground": {"window_title": "Google - Chrome"},
                "screen": {"scene_hint": "browser"},
            },
        )
        assert scene.scene_id == "browser_desktop_mismatch"
        assert scene.primary_preset_id == "advance"
        assert "桌面" in scene.body
