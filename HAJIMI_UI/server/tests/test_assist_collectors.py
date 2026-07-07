"""Assist collector 单测。"""
from server.services.assist.collectors.browser import BrowserHeuristicCollector
from server.services.assist.collectors.desktop import DesktopShortcutCollector
from server.services.assist.collectors.wps import WPSHeuristicCollector
from server.services.assist.types import AssistContext, CandidateElement


def _ctx(**kwargs) -> AssistContext:
    bundle = kwargs.pop("bundle", {})
    return AssistContext(bundle=bundle, **kwargs)


class TestDesktopShortcutCollector:
    def test_supports_desktop_scene(self):
        col = DesktopShortcutCollector()
        ctx = _ctx(bundle={"screen": {"scene_hint": "desktop"}})
        assert col.supports(ctx)

    def test_collect_with_bbox(self):
        col = DesktopShortcutCollector()
        ctx = _ctx(
            bundle={
                "screen": {"scene_hint": "desktop"},
                "local_candidates": [
                    {"name": "Google Chrome", "bbox": [10, 20, 50, 70]},
                ],
            }
        )
        items = col.collect(ctx)
        assert len(items) == 1
        assert items[0].name == "Google Chrome"
        assert items[0].source == "desktop_shortcut"

    def test_skips_candidates_without_bbox(self):
        col = DesktopShortcutCollector()
        ctx = _ctx(
            bundle={
                "local_candidates": [{"name": "Chrome"}],
            }
        )
        assert col.collect(ctx) == []


class TestBrowserHeuristicCollector:
    def test_supports_browser_process(self):
        col = BrowserHeuristicCollector()
        ctx = _ctx(bundle={"foreground": {"process_name": "chrome.exe"}})
        assert col.supports(ctx)

    def test_collect_address_bar(self):
        col = BrowserHeuristicCollector()
        ctx = _ctx(
            bundle={
                "screen": {"scene_hint": "browser"},
                "foreground": {"rect": [0, 0, 1920, 1080]},
            }
        )
        items = col.collect(ctx)
        names = {i.name for i in items}
        assert "地址栏" in names


class TestWPSHeuristicCollector:
    def test_supports_wps_title(self):
        col = WPSHeuristicCollector()
        ctx = _ctx(bundle={"foreground": {"window_title": "WPS 表格"}})
        assert col.supports(ctx)

    def test_collect_merge_cells(self):
        col = WPSHeuristicCollector()
        ctx = _ctx(
            bundle={
                "screen": {"scene_hint": "wps"},
                "foreground": {"rect": [0, 0, 1920, 1080]},
            }
        )
        items = col.collect(ctx)
        names = {i.name for i in items}
        assert "合并单元格" in names
