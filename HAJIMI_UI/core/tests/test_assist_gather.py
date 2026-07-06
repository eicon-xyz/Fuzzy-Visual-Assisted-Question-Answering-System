"""AssistBundle 采集单测。"""
from core.assist_collect.gather import (
    _infer_scene_hint,
    foreground_window_title,
    gather_assist_bundle,
)


class TestInferSceneHint:
    def test_desktop_explorer(self):
        assert _infer_scene_hint("", "explorer.exe", "Progman") == "desktop"

    def test_browser_chrome(self):
        assert _infer_scene_hint("Google - Chrome", "chrome.exe", "") == "browser"

    def test_wps_title(self):
        assert _infer_scene_hint("WPS 表格", "et.exe", "") == "wps"

    def test_unknown(self):
        assert _infer_scene_hint("Notepad", "notepad.exe", "") == "unknown"


class TestGatherAssistBundle:
    def test_bundle_has_required_keys(self):
        bundle = gather_assist_bundle()
        assert "foreground" in bundle
        assert "screen" in bundle
        assert "local_candidates" in bundle
        assert "scene_hint" in bundle["screen"]

    def test_foreground_window_title_fallback(self):
        title = foreground_window_title({"foreground": {"window_title": "Test Window"}})
        assert title == "Test Window"

    def test_foreground_window_title_default(self):
        title = foreground_window_title({})
        assert isinstance(title, str)
        assert title
