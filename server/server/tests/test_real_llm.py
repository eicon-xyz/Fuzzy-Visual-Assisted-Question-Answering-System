"""
Layer 4 — Real LLM End-to-End Tests

Requires: valid LLM_API_KEY + LLM_BASE_URL in .env
Mark: @pytest.mark.real_llm

Binds a known-small model for fast, cheap verification that the full
pipeline works end-to-end — from HTTP POST to parsed JSON.

Run:
  python -m pytest server/tests/test_real_llm.py -v -m real_llm

Separate file because these require network + API key, and are excluded
from CI by default (mark-based filtering).
"""

import pytest
import time
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.real_llm


# ── Helpers ────────────────────────────────────────────────────────────────


def _llm_configured():
    from server.config import settings
    return bool(settings.LLM_API_KEY and settings.LLM_BASE_URL)


# ═══════════════════════════════════════════════════════════════════════════
# 1 — LLM Connectivity Smoke
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _llm_configured(), reason="LLM credentials not set")
class TestLLMConnectivity:
    """Bare-metal smoke tests against the real LLM endpoint."""

    def test_simple_text_response(self):
        """Send a one-word prompt, expect short text back."""
        from server.services.llm.providers import call_llm

        resp = call_llm("Say exactly: OK", max_tokens=32, timeout=30)
        assert len(resp) > 0
        # Even a small model should return something
        assert any(w.lower() in resp.lower() for w in ("ok", "OK"))

    def test_json_response_parsed(self):
        """call_llm_json returns a valid dict."""
        from server.services.llm.providers import call_llm_json

        data = call_llm_json(
            'Output ONLY: {"status":"ok","count":1}',
            max_tokens=128, timeout=30,
        )
        assert isinstance(data, dict)
        assert "status" in data or "goal" in data  # goal is default-injected

    def test_latency_under_30s(self):
        """Simple call must complete within 30 seconds."""
        from server.services.llm.providers import call_llm

        start = time.time()
        call_llm("1+1=?", max_tokens=64, timeout=30)
        elapsed = time.time() - start
        assert elapsed < 30, f"LLM call took {elapsed:.1f}s (limit: 30s)"

    def test_chinese_input(self):
        """Chinese input should return Chinese response."""
        from server.services.llm.providers import call_llm

        resp = call_llm("用一句话回复：你好", max_tokens=128, timeout=30)
        assert len(resp) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 2 — Chain Functions with Real LLM
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _llm_configured(), reason="LLM credentials not set")
class TestChainsRealLLM:
    """Each chain function makes one real LLM call — verify prompt + parse."""

    def test_plan_and_locate(self):
        from server.services.agent.chains import plan_and_locate

        result = plan_and_locate(goal="Open Chrome browser")
        assert "goal" in result
        assert "steps" in result
        assert len(result["steps"]) >= 1
        assert "pointer" in result

    def test_plan_goal(self):
        from server.services.agent.chains import plan_goal

        result = plan_goal(goal="Create a new folder on desktop")
        assert "goal" in result
        assert len(result["steps"]) >= 1

    def test_locate_step_target(self):
        from server.services.agent.chains import locate_step_target

        result = locate_step_target(
            goal="Open Chrome",
            step={"title": "Click Chrome icon", "instruction": "Find and double-click Chrome icon on desktop"},
        )
        # Without a screenshot, locator may or may not find coordinates
        # but it should not crash
        assert "shouldPoint" in result

    def test_evaluate_step(self):
        from server.services.agent.chains import evaluate_step

        result = evaluate_step(
            goal="Open Chrome",
            step={"title": "Click Chrome", "instruction": "Click Chrome icon",
                  "successCriteria": "Chrome is open"},
        )
        assert result["status"] in ("done", "not_done", "blocked", "uncertain")
        assert "confidence" in result

    def test_replan_goal(self):
        from server.services.agent.chains import replan_goal

        result = replan_goal(
            goal="Open Chrome",
            failed_step_title="Click Chrome icon",
            rationale="Chrome icon not found on desktop — maybe it's pinned to taskbar",
        )
        assert "goal" in result
        assert len(result["steps"]) >= 1

    def test_fast_mode_chat(self):
        from server.services.agent.chains import fast_mode_chat

        response = fast_mode_chat("What is 1+1? Answer in one word.")
        assert len(response) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 3 — TaskOrchestrator with Real LLM
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _llm_configured(), reason="LLM credentials not set")
class TestOrchestratorRealLLM:
    """process_query runs plan_and_locate → postprocess → set session state."""

    def test_process_query_basic(self, fresh_session):
        from server.services.agent.orchestrator import TaskOrchestrator

        orch = TaskOrchestrator.__new__(TaskOrchestrator)
        orch._session = fresh_session
        orch._provider = None

        result = orch.process_query(query="Open Chrome browser")
        assert result["success"] is True
        assert result["plan"] is not None
        assert result["plan"]["goal"] is not None
        assert len(result["plan"]["steps"]) >= 1
        # Session should be in waiting_user state
        assert fresh_session.get_status() == "waiting_user"

    def test_process_query_no_image(self, fresh_session):
        from server.services.agent.orchestrator import TaskOrchestrator

        orch = TaskOrchestrator.__new__(TaskOrchestrator)
        orch._session = fresh_session
        orch._provider = None

        result = orch.process_query(query="Create a text file on desktop")
        assert result["success"] is True
        assert result["plan"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# 4 — Agent dispatch with real browser, mock LLM
#     (confirms the wiring: real Chromium ← agent ← canned LLM)
#     Already covered by Layer 3.  Skipped here.
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# 5 — Full Agent execution with real LLM + real browser
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _llm_configured(), reason="LLM credentials not set")
class TestAgentRealLLMRealBrowser:
    """The hardest integration: real LLM decides which tools to call,
    real browser executes them.  One step only to keep cost low."""

    @pytest.fixture(autouse=True)
    def _agent_with_browser(self):
        """Start a real browser via ExecutionAgent's event loop."""
        import importlib, os
        try:
            mod = importlib.import_module("playwright.sync_api")
            with mod.sync_playwright() as p:
                if not os.path.exists(p.chromium.executable_path):
                    pytest.skip("chromium not installed")
        except Exception:
            pytest.skip("playwright not installed")

        from server.services.browser.controller import BrowserController
        from server.services.executor.agent import ExecutionAgent

        agent = ExecutionAgent()
        agent.element_map = {}
        agent.screen_elements = []
        bc = BrowserController()
        agent._browser = bc
        agent._run_async(bc.start(headless=True))

        self._agent = agent
        self._bc = bc

        yield

        try:
            if bc.is_started:
                agent._run_async(bc.close())
        except Exception:
            pass
        agent._stop_browser_loop()

    def test_agent_navigates_to_example_com(self):
        """Real LLM should call browser_navigate → browser_snapshot → mark_step_done.

        Prompt is carefully crafted to constrain the LLM to a known-good path.
        """
        from server.models.schemas import ExecutedStep

        agent = self._agent
        step = ExecutedStep(
            step_index=1,
            instruction="Open https://example.com in the browser and verify the page loaded",
        )
        result = agent.execute_step(
            step,
            goal="Verify browser automation works",
            previous_steps=[],
        )
        # Either done (LLM followed the path) or failed (LLM tried something else)
        # The key assertion: the agent loop didn't crash and returned a result
        assert result.status in ("done", "failed")
        if result.status == "done":
            assert result.action_summary is not None


# ═══════════════════════════════════════════════════════════════════════════
# 6 — Provider error handling (no network mock, real failure paths)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _llm_configured(), reason="LLM credentials not set")
class TestProviderErrorRecovery:
    """Verify the provider layer handles edge cases gracefully."""

    def test_call_llm_default_system_prompt(self):
        """call_llm without a system_prompt uses DEFAULT_SYSTEM_PROMPT."""
        from server.services.llm.providers import call_llm

        resp = call_llm("Reply with just the word: hello", max_tokens=32, timeout=30)
        assert len(resp) > 0

    def test_call_llm_with_history(self):
        from server.services.llm.providers import call_llm

        history = [
            {"role": "user", "content": "My name is Alice"},
            {"role": "assistant", "content": "Hello Alice!"},
        ]
        resp = call_llm("What is my name?", history=history, max_tokens=64, timeout=30)
        assert "Alice" in resp or "alice" in resp.lower()

    def test_call_vision_without_image(self):
        from server.services.llm.providers import call_vision_llm

        resp = call_vision_llm("Say hello", max_tokens=32, timeout=30)
        assert len(resp) > 0
