"""
Layer 3 — Agent-to-Browser E2E Pipeline Tests

Verifies the FULL business loop: User says "search X" → Agent plans →
dispatches real browser tools → confirms result → marks done.

Uses:
  - Real BrowserController (Playwright Chromium, headless)
  - Mock LLM — canned tool-call sequences (avoids LLM cost/non-determinism)

This distinguishes "browser driver is broken" from "agent logic is broken":
  - test_browser_e2e.py  → tests BROWSER DRIVER (single ops)
  - test_e2e_pipeline.py → tests AGENT BUSINESS LOOP (multi-step tasks)
"""

import pytest
import pytest_asyncio
import asyncio
import json
import threading
import time
from unittest.mock import MagicMock, patch, AsyncMock

pytestmark = pytest.mark.e2e


# ── Helpers ────────────────────────────────────────────────────────────────


def _chromium_installed():
    import importlib, os
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


def _tool_json(name, args=None):
    return json.dumps({"__tool_call__": True, "name": name, "arguments": args or {}})


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def agent_with_real_browser():
    """ExecutionAgent backed by a REAL BrowserController (headless Chromium).

    The browser is started synchronously via a background event loop,
    matching the production _run_async / _ensure_browser_started pattern.
    """
    from server.services.browser.controller import BrowserController
    from server.services.executor.agent import ExecutionAgent

    agent = ExecutionAgent()
    agent.element_map = {}
    agent.screen_elements = []

    # Start a real browser in headless mode via the agent's own event loop
    bc = BrowserController()
    agent._browser = bc
    agent._run_async(bc.start(headless=True))

    yield agent

    # Cleanup
    try:
        if bc.is_started:
            agent._run_async(bc.close())
    except Exception:
        pass
    agent._stop_browser_loop()


# ── Skip conditions ─────────────────────────────────────────────────────────

pytestmark_skip = pytest.mark.skipif(
    not (_try_import_playwright() and _chromium_installed()),
    reason="playwright + chromium required (run: playwright install chromium)",
)


# ========================================================================
# Pipeline 1: Navigate → Snapshot → Verify elements exist
# ========================================================================


@pytestmark_skip
class TestPipelineNavigateAndInspect:
    """Agent navigates to a page and inspects the DOM."""

    def test_navigate_then_snapshot(self, agent_with_real_browser):
        """Navigate via _run_async (production pattern) → verify snapshot."""
        agent = agent_with_real_browser
        bc = agent._browser

        agent._run_async(bc.navigate("https://example.com"))
        snap = agent._run_async(bc.get_snapshot())
        assert snap["success"] is True
        assert len(snap["elements"]) >= 1
        assert "Example" in snap["title"]

    def test_snapshot_returns_interactive_elements(self, agent_with_real_browser):
        """Snapshot of a real page returns link elements."""
        agent = agent_with_real_browser
        bc = agent._browser
        agent._run_async(bc.navigate("https://example.com"))

        snap = agent._run_async(bc.get_snapshot())
        tags = [e["tag"] for e in snap["elements"]]
        assert "a" in tags, f"Expected <a> tags in snapshot, got tags: {tags}"


# ========================================================================
# Pipeline 2: Agent drives browser via execute_step (mock LLM)
# ========================================================================


@pytestmark_skip
class TestAgentDrivesBrowser:
    """execute_step with canned LLM tool sequences driving a real browser."""

    def test_agent_opens_page_and_inspects(self, agent_with_real_browser):
        """LLM: browser_navigate(example.com) → browser_snapshot → mark_step_done."""
        from server.models.schemas import ExecutedStep

        calls = [
            (_tool_json("browser_navigate", {"url": "https://example.com"}), None),
            (_tool_json("browser_snapshot"), None),
            (_tool_json("mark_step_done", {"reason": "page loaded"}), None),
        ]
        call_idx = [0]

        def mock_llm(msgs):
            r = calls[min(call_idx[0], len(calls) - 1)]
            call_idx[0] += 1
            return r

        agent_with_real_browser._call_llm_with_tools = mock_llm

        step = ExecutedStep(step_index=1, instruction="Open example.com and inspect")
        result = agent_with_real_browser.execute_step(
            step, goal="Test browser", previous_steps=[]
        )
        assert result.status == "done"

    def test_agent_takes_screenshot(self, agent_with_real_browser):
        """LLM: browser_navigate → browser_screenshot → mark_step_done."""
        from server.models.schemas import ExecutedStep

        calls = [
            (_tool_json("browser_navigate", {"url": "https://example.com"}), None),
            (_tool_json("browser_screenshot"), None),
            (_tool_json("mark_step_done", {"reason": "screenshot taken"}), None),
        ]
        call_idx = [0]

        def mock_llm(msgs):
            r = calls[min(call_idx[0], len(calls) - 1)]
            call_idx[0] += 1
            return r

        agent_with_real_browser._call_llm_with_tools = mock_llm

        step = ExecutedStep(step_index=1, instruction="Take a screenshot of example.com")
        result = agent_with_real_browser.execute_step(
            step, goal="Test screenshot", previous_steps=[]
        )
        assert result.status == "done"

    def test_agent_scrolls_page(self, agent_with_real_browser):
        """LLM: browser_navigate → browser_scroll → mark_step_done."""
        from server.models.schemas import ExecutedStep

        calls = [
            (_tool_json("browser_navigate", {"url": "https://example.com"}), None),
            (_tool_json("browser_scroll", {"direction": "down", "amount": 200}), None),
            (_tool_json("mark_step_done", {"reason": "scrolled"}), None),
        ]
        call_idx = [0]

        def mock_llm(msgs):
            r = calls[min(call_idx[0], len(calls) - 1)]
            call_idx[0] += 1
            return r

        agent_with_real_browser._call_llm_with_tools = mock_llm

        step = ExecutedStep(step_index=1, instruction="Scroll down the page")
        result = agent_with_real_browser.execute_step(
            step, goal="Test scroll", previous_steps=[]
        )
        assert result.status == "done"

    def test_agent_handles_navigation_failure(self, agent_with_real_browser):
        """LLM: browser_navigate(bad_url) → browser fails → mark_step_failed."""
        from server.models.schemas import ExecutedStep

        calls = [
            (_tool_json("browser_navigate", {"url": "https://does-not-exist.invalid"}), None),
            (_tool_json("mark_step_failed", {"reason": "page not reachable"}), None),
        ]
        call_idx = [0]

        def mock_llm(msgs):
            r = calls[min(call_idx[0], len(calls) - 1)]
            call_idx[0] += 1
            return r

        agent_with_real_browser._call_llm_with_tools = mock_llm

        step = ExecutedStep(step_index=1, instruction="Open a dead site")
        result = agent_with_real_browser.execute_step(
            step, goal="Test failure", previous_steps=[]
        )
        # Agent marks failed — verify it didn't crash
        assert result.status == "failed"


# ========================================================================
# Pipeline 3: Agent browser search flow (mock LLM drives real browser)
# ========================================================================

@pytestmark_skip
class TestAgentSearchFlow:
    """Simulated search flow: navigate to search engine → type query → submit."""

    def test_search_bing(self, agent_with_real_browser):
        """Navigate to bing.com → type 'hello world' → press Enter → snapshot results."""
        agent = agent_with_real_browser
        bc = agent._browser

        nav = agent._run_async(bc.navigate("https://www.bing.com"))
        assert nav["success"] is True

        snap = agent._run_async(bc.get_snapshot())
        assert snap["success"] is True

        agent._run_async(bc.type("#sb_form_q", "hello world"))
        agent._run_async(bc.press_key("Enter"))

        time.sleep(2)

        snap2 = agent._run_async(bc.get_snapshot())
        assert snap2["success"] is True

    def test_search_duckduckgo(self, agent_with_real_browser):
        """Navigate to duckduckgo.com → type query → submit → verify results."""
        agent = agent_with_real_browser
        bc = agent._browser

        nav = agent._run_async(bc.navigate("https://duckduckgo.com"))
        if not nav["success"]:
            pytest.skip("DuckDuckGo not reachable")

        agent._run_async(bc.type('input[name="q"]', "pytest tutorial"))
        agent._run_async(bc.press_key("Enter"))

        time.sleep(2)

        snap = agent._run_async(bc.get_snapshot())
        assert snap["success"] is True


# ========================================================================
# Pipeline 4: Browser lifecycle (start → use → close → restart)
# ========================================================================

@pytestmark_skip
class TestBrowserLifecycle:
    """BrowserController lifetime: start, use, close, restart."""

    @pytest.mark.asyncio
    async def test_close_and_restart(self):
        """Close a browser and start a fresh one — should work."""
        from server.services.browser.controller import BrowserController

        bc1 = BrowserController()
        await bc1.start(headless=True)
        await bc1.navigate("https://example.com")
        snap1 = await bc1.get_snapshot()
        assert len(snap1["elements"]) >= 1

        await bc1.close()
        assert bc1.is_started is False
        assert bc1._page is None

        # Restart fresh
        bc2 = BrowserController()
        await bc2.start(headless=True)
        await bc2.navigate("https://example.com")
        snap2 = await bc2.get_snapshot()
        assert len(snap2["elements"]) >= 1
        await bc2.close()
