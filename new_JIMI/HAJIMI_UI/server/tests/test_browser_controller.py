"""
Unit tests for BrowserController — mock Playwright's async API.

Usage:
    cd D:/HAJI/HAJIMI_UI
    python -m pytest server/tests/test_browser_controller.py -v
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_page():
    """Return a MagicMock that mimics a Playwright Page with async methods."""
    page = MagicMock()
    page.goto = AsyncMock()
    page.title = AsyncMock(return_value="Test Page")
    page.url = "https://example.com"
    page.locator = MagicMock()
    page.evaluate = AsyncMock(return_value=[])
    # locator().first pattern
    locator = MagicMock()
    locator.first = locator
    locator.click = AsyncMock()
    locator.fill = AsyncMock()
    locator.focus = AsyncMock()
    locator.type = AsyncMock()
    locator.text_content = AsyncMock(return_value="Click Me")
    locator.evaluate = AsyncMock(return_value="button")
    page.locator.return_value = locator
    return page


@pytest.fixture
def mock_browser(mock_page):
    """Return a MagicMock that mimics a Playwright Browser."""
    browser = MagicMock()
    browser.new_page = AsyncMock(return_value=mock_page)
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def mock_playwright(mock_browser):
    """Return a MagicMock that mimics a Playwright instance (after .start())."""
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=mock_browser)
    return pw


@pytest_asyncio.fixture
async def controller(mock_playwright):
    """Return a started BrowserController with mocked Playwright.

    Patches playwright.async_api.async_playwright at the source module so
    that the import inside BrowserController.start() picks up our mock.
    """
    from server.services.browser.controller import BrowserController

    bc = BrowserController()
    # async_playwright() returns a context manager; .start() returns the
    # Playwright instance (our mock_playwright).
    context_manager = MagicMock()
    context_manager.start = AsyncMock(return_value=mock_playwright)
    with patch(
        "playwright.async_api.async_playwright",
        return_value=context_manager,
    ):
        await bc.start(headless=True)
    return bc


# ── Lifecycle ──────────────────────────────────────────────────────────────

class TestBrowserLifecycle:
    """BrowserController start/close lifecycle."""

    @pytest.mark.asyncio
    async def test_start_launches_chromium(self, controller, mock_page):
        assert controller.is_started is True
        assert controller._page is not None

    @pytest.mark.asyncio
    async def test_start_idempotent(self, controller):
        """Calling start() twice should not crash or create a second browser."""
        await controller.start()  # already started — should log and return
        assert controller.is_started is True

    @pytest.mark.asyncio
    async def test_close_cleans_up(self, controller):
        await controller.close()
        assert controller.is_started is False
        assert controller._page is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self, controller):
        await controller.close()
        await controller.close()  # second close should not crash
        assert controller.is_started is False

    @pytest.mark.asyncio
    async def test_is_started_before_start(self):
        from server.services.browser.controller import BrowserController

        bc = BrowserController()
        assert bc.is_started is False


# ── Navigate ───────────────────────────────────────────────────────────────

class TestNavigate:
    """Tiered wait_until navigation."""

    @pytest.mark.asyncio
    async def test_navigate_success_first_tier(self, controller, mock_page):
        mock_page.goto = AsyncMock(return_value=MagicMock(status=200))
        result = await controller.navigate("https://example.com")
        assert result["success"] is True
        assert result["title"] == "Test Page"
        assert result["wait_until"] == "commit"  # first tier succeeded
        # Verify first call used "commit"
        mock_page.goto.assert_called_with(
            "https://example.com", wait_until="commit", timeout=8_000
        )

    @pytest.mark.asyncio
    async def test_navigate_auto_adds_https(self, controller, mock_page):
        mock_page.goto = AsyncMock(return_value=MagicMock(status=200))
        result = await controller.navigate("example.com")
        assert result["success"] is True
        mock_page.goto.assert_called_with(
            "https://example.com", wait_until="commit", timeout=8_000
        )

    @pytest.mark.asyncio
    async def test_navigate_fallback_on_tier_failure(self, controller, mock_page):
        """If commit fails, falls back to load."""
        mock_page.goto = AsyncMock(
            side_effect=[
                TimeoutError("commit timed out"),  # tier 1 fails
                MagicMock(status=200),  # tier 2 succeeds
            ]
        )
        result = await controller.navigate("https://spa.example.com")
        assert result["success"] is True
        assert result["wait_until"] == "load"
        assert mock_page.goto.call_count == 2

    @pytest.mark.asyncio
    async def test_navigate_partial_load_detection(self, controller, mock_page):
        """All tiers fail but URL changed — partial success."""
        mock_page.goto = AsyncMock(side_effect=TimeoutError("all failed"))
        # Page URL changed despite goto failure (partial load)
        mock_page.url = "https://spa.example.com/dashboard"
        result = await controller.navigate("https://spa.example.com")
        assert result["success"] is True
        assert result["wait_until"] == "partial"
        assert "warning" in result

    @pytest.mark.asyncio
    async def test_navigate_complete_failure(self, controller, mock_page):
        """All tiers fail and URL stays about:blank."""
        mock_page.goto = AsyncMock(side_effect=TimeoutError("all failed"))
        mock_page.url = "about:blank"
        result = await controller.navigate("https://dead.example.com")
        assert result["success"] is False
        assert "error" in result


# ── Click ──────────────────────────────────────────────────────────────────

class TestClick:
    @pytest.mark.asyncio
    async def test_click_success(self, controller, mock_page):
        result = await controller.click("#submit")
        assert result["success"] is True
        assert result["selector"] == "#submit"
        assert "clicked" in result["action_summary"]

    @pytest.mark.asyncio
    async def test_click_not_found(self, controller, mock_page):
        locator = mock_page.locator.return_value
        locator.click = AsyncMock(side_effect=Exception("Element not found"))
        result = await controller.click("#missing")
        assert result["success"] is False
        assert "not found" in result["error"]


# ── Type ───────────────────────────────────────────────────────────────────

class TestType:
    @pytest.mark.asyncio
    async def test_type_success(self, controller, mock_page):
        result = await controller.type("#input", "hello")
        assert result["success"] is True
        assert result["text"] == "hello"
        locator = mock_page.locator.return_value
        locator.evaluate.assert_called_once()  # JS value set
        # Verify it dispatched input/change events
        call_args = locator.evaluate.call_args[0][0]
        assert "el.value = 'hello'" in call_args
        assert "dispatchEvent" in call_args

    @pytest.mark.asyncio
    async def test_type_not_found(self, controller, mock_page):
        locator = mock_page.locator.return_value
        locator.evaluate = AsyncMock(side_effect=Exception("No such element"))
        result = await controller.type("#missing", "text")
        assert result["success"] is False


# ── Snapshot ───────────────────────────────────────────────────────────────

class TestSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_empty_page(self, controller, mock_page):
        mock_page.evaluate = AsyncMock(return_value=[])
        result = await controller.get_snapshot()
        assert result["success"] is True
        assert len(result["elements"]) == 0
        assert "0 elements" in result["action_summary"]

    @pytest.mark.asyncio
    async def test_snapshot_with_elements(self, controller, mock_page):
        mock_page.evaluate = AsyncMock(
            return_value=[
                {
                    "tag": "button",
                    "text": "Submit",
                    "selector": "#submit",
                    "href": "",
                    "type": "submit",
                    "name": "",
                    "id": "submit",
                },
                {
                    "tag": "a",
                    "text": "Home",
                    "selector": "a.nav",
                    "href": "/home",
                    "type": "",
                    "name": "",
                    "id": "",
                },
            ]
        )
        result = await controller.get_snapshot()
        assert result["success"] is True
        assert len(result["elements"]) == 2
        assert "snapshot_text" in result
        assert "Submit" in result["snapshot_text"]

    @pytest.mark.asyncio
    async def test_snapshot_text_truncated(self, controller, mock_page):
        long_text = "A" * 200
        mock_page.evaluate = AsyncMock(
            return_value=[
                {
                    "tag": "span",
                    "text": long_text,
                    "selector": "span",
                    "href": "",
                    "type": "",
                    "name": "",
                    "id": "",
                },
            ]
        )
        result = await controller.get_snapshot()
        # Text is truncated client-side by JS; we just verify it doesn't blow up
        assert result["success"] is True
        assert len(result["snapshot_text"]) < 5000  # compact format

    @pytest.mark.asyncio
    async def test_snapshot_includes_title_and_url(self, controller, mock_page):
        mock_page.title = AsyncMock(return_value="My Dashboard")
        mock_page.url = "https://app.example.com/dashboard"
        mock_page.evaluate = AsyncMock(return_value=[])
        result = await controller.get_snapshot()
        assert result["title"] == "My Dashboard"
        assert "dashboard" in result["url"]


# ── Scroll ─────────────────────────────────────────────────────────────────

class TestScroll:
    @pytest.mark.asyncio
    async def test_scroll_down(self, controller, mock_page):
        result = await controller.scroll("down", 500)
        assert result["success"] is True
        mock_page.evaluate.assert_called_once_with("window.scrollBy(0, 500)")

    @pytest.mark.asyncio
    async def test_scroll_up(self, controller, mock_page):
        result = await controller.scroll("up", 300)
        assert result["success"] is True
        mock_page.evaluate.assert_called_once_with("window.scrollBy(0, -300)")


# ── _ensure_started ────────────────────────────────────────────────────────

class TestEnsureStarted:
    @pytest.mark.asyncio
    async def test_unstarted_raises(self):
        from server.services.browser.controller import BrowserController

        bc = BrowserController()
        with pytest.raises(RuntimeError, match="not started"):
            await bc.navigate("https://example.com")
        with pytest.raises(RuntimeError, match="not started"):
            await bc.click("#btn")
        with pytest.raises(RuntimeError, match="not started"):
            await bc.get_snapshot()


# ── Screenshot ─────────────────────────────────────────────────────────

class TestScreenshot:
    @pytest.mark.asyncio
    async def test_screenshot_returns_base64(self, controller, mock_page):
        mock_page.screenshot = AsyncMock(return_value=b'\xff\xd8\xff\xe0\x00\x10JFIF')
        result = await controller.screenshot()
        assert result["success"] is True
        assert result["image_b64"].startswith("data:image/jpeg;base64,")
        assert len(result["image_b64"]) > 30


# ── Press Key ────────────────────────────────────────────────────────────────

class TestPressKey:
    @pytest.mark.asyncio
    async def test_press_key_enter(self, controller, mock_page):
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()
        result = await controller.press_key("Enter")
        assert result["success"] is True
        assert result["keys"] == "Enter"
        mock_page.keyboard.press.assert_called_once_with("Enter")

    @pytest.mark.asyncio
    async def test_press_key_combo(self, controller, mock_page):
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()
        result = await controller.press_key("Control+a")
        assert result["success"] is True
        mock_page.keyboard.press.assert_called_once_with("Control+a")
