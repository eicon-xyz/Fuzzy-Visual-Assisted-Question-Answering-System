"""
E2E smoke tests for BrowserController — uses real Playwright Chromium.

These tests require: playwright install chromium
Skip if Chromium is not installed.
"""

import pytest
import pytest_asyncio

pytestmark = pytest.mark.e2e


def _chromium_installed():
    """Check if Playwright Chromium binary exists."""
    import importlib
    import os
    try:
        mod = importlib.import_module("playwright.sync_api")
        with mod.sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:
        return False


def _try_import_playwright():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


@pytest_asyncio.fixture
async def browser():
    """Start a real BrowserController for E2E testing."""
    from server.services.browser.controller import BrowserController
    bc = BrowserController()
    await bc.start(headless=True)
    yield bc
    await bc.close()


@pytest.mark.skipif(
    not _try_import_playwright(),
    reason="playwright not installed",
)
@pytest.mark.skipif(
    not _chromium_installed(),
    reason="chromium browser not installed (run: playwright install chromium)",
)
class TestBrowserE2E:
    """Real-browser round-trip tests."""

    @pytest.mark.asyncio
    async def test_navigate_and_snapshot(self, browser):
        """Navigate to a static page, verify snapshot has elements."""
        result = await browser.navigate("https://example.com")
        assert result["success"] is True
        assert result["title"] is not None

        snapshot = await browser.get_snapshot()
        assert snapshot["success"] is True
        # example.com has at least one <a> tag
        assert len(snapshot["elements"]) >= 1
        assert "Example Domain" in snapshot["title"] or "Example" in snapshot["title"]

    @pytest.mark.asyncio
    async def test_screenshot_returns_image(self, browser):
        """Screenshot of a real page produces a valid data URI."""
        await browser.navigate("https://example.com")
        result = await browser.screenshot()
        assert result["success"] is True
        assert result["image_b64"].startswith("data:image/jpeg;base64,")
        # base64 should be non-trivial (> 500 chars)
        assert len(result["image_b64"]) > 500

    @pytest.mark.asyncio
    async def test_scroll_changes_viewport(self, browser):
        """Scroll on a real page should not throw."""
        await browser.navigate("https://example.com")
        result = await browser.scroll("down", 100)
        assert result["success"] is True
