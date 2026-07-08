"""
Layer 2 — FastAPI Route Integration Tests

FastAPI TestClient against real app router. Dependencies mocked at definition site.
No real LLM, no browser, no display needed.
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from server.config import settings
from server.main import app
from server.services.executor import engine


def _fake_response():
    from server.models.schemas import (
        ProcessResponse, Intent, Blueprint, ExecutedStep
    )
    return ProcessResponse(
        task_id="task-test-001", success=True, goal="Open Chrome browser",
        intent=Intent(category="ui_navigation", summary="test", confidence=0.9, needs_clarification=False),
        ui_elements=[],
        blueprint=Blueprint(name="test", total_steps=2, current_step=1, state="generated"),
        steps=[
            ExecutedStep(step_index=1, instruction="Open browser", status="pending"),
            ExecutedStep(step_index=2, instruction="Navigate", status="pending"),
        ],
    )


def _headers():
    return {"X-Demo-Key": settings.DEMO_KEY}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_state():
    engine._event_queues.clear()
    engine._cancel_flags.clear()
    engine._cancel_events.clear()
    yield


# ========================================================================
# Health (no auth required)
# ========================================================================


class TestHealth:
    def test_degraded(self, client):
        with patch("httpx.Client") as m:
            m.return_value.__enter__.return_value.get.side_effect = Exception("down")
            r = client.get("/api/demo/health")
            assert r.status_code == 503

    def test_ok(self, client):
        with patch("httpx.Client") as m:
            mr = MagicMock()
            mr.status_code = 200
            mr.json.return_value = {"ready": True, "device": "cuda"}
            m.return_value.__enter__.return_value.get.return_value = mr
            r = client.get("/api/demo/health")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"


# ========================================================================
# Auth (tested against /execute which has Depends(verify_demo_key))
# ========================================================================


class TestAuth:
    def test_no_key_401(self, client):
        r = client.post("/api/demo/execute", json={"query": "test"})
        assert r.status_code == 401

    def test_wrong_key_401(self, client):
        r = client.post("/api/demo/execute", json={"query": "test"},
                        headers={"X-Demo-Key": "wrong"})
        assert r.status_code == 401

    def test_correct_key_passes_auth(self, client):
        """Auth passes, hits planning (which we mock)."""
        with patch("server.services.planning.router.process_query", return_value=_fake_response()), \
             patch("server.storage.memory.task_store.create"), \
             patch("server.database.repository.TaskRepository.create_from_response"), \
             patch("server.services.executor.agent.ExecutionAgent") as MockAgent:
            MockAgent.return_value.execute_step.return_value = MagicMock(status="done")
            MockAgent.return_value.close_browser = MagicMock()
            r = client.post("/api/demo/execute", json={"query": "Open Chrome"},
                            headers=_headers())
            assert r.status_code == 200
            assert r.json()["success"] is True


# ========================================================================
# POST /execute
# ========================================================================


class TestExecute:
    def test_redline_blocks(self, client):
        r = client.post("/api/demo/execute",
                        json={"query": "delete all files"}, headers=_headers())
        d = r.json()
        assert d["success"] is False
        assert d["error"]["code"] == "REDLINE"

    def test_success(self, client):
        with patch("server.services.planning.router.process_query", return_value=_fake_response()), \
             patch("server.storage.memory.task_store.create"), \
             patch("server.database.repository.TaskRepository.create_from_response"), \
             patch("server.services.executor.agent.ExecutionAgent") as MockAgent:
            MockAgent.return_value.execute_step.return_value = MagicMock(status="done")
            MockAgent.return_value.close_browser = MagicMock()
            r = client.post("/api/demo/execute", json={"query": "Open Chrome"},
                            headers=_headers())
            d = r.json()
            assert d["success"] is True
            assert d["task_id"] is not None
            assert len(d["plan"]["steps"]) == 2

    def test_planning_failed(self, client):
        with patch("server.services.planning.router.process_query", side_effect=RuntimeError("down")):
            r = client.post("/api/demo/execute", json={"query": "X"}, headers=_headers())
            d = r.json()
            assert d["success"] is False
            assert d["error"]["code"] == "PLANNING_FAILED"

    def test_plan_returned_false_success(self, client):
        bad = _fake_response()
        bad.success = False
        from server.models.schemas import RedlineInfo
        bad.redline = RedlineInfo(triggered=True, category="privacy", message="blocked")
        with patch("server.services.planning.router.process_query", return_value=bad):
            r = client.post("/api/demo/execute", json={"query": "X"}, headers=_headers())
            d = r.json()
            assert d["success"] is False


# ========================================================================
# GET /stream/{task_id}  (no auth)
# ========================================================================


class TestStream:
    def test_receives_events(self, client):
        q = engine.register_task("task-s1")
        q.put({"event": "step_start", "data": {"step_index": 1}})
        q.put({"event": "task_done", "data": {"task_id": "task-s1"}})
        r = client.get("/api/demo/stream/task-s1")
        assert r.status_code == 200
        assert "event: heartbeat" in r.text
        assert "event: step_start" in r.text


# ========================================================================
# POST /cancel
# ========================================================================


class TestCancel:
    def test_nonexistent(self, client):
        r = client.post("/api/demo/cancel", json={"task_id": "no-such"}, headers=_headers())
        assert r.json()["success"] is False

    def test_existing(self, client):
        engine.register_task("task-c1")
        engine.cancel_task("task-c1")
        r = client.post("/api/demo/cancel", json={"task_id": "task-c1"}, headers=_headers())
        assert r.json()["success"] is True


# ========================================================================
# POST /process (legacy)
# ========================================================================


class TestLegacy:
    def test_process(self, client):
        with patch("server.services.planning.router.process_query", return_value=_fake_response()), \
             patch("server.storage.memory.task_store.create"), \
             patch("server.database.repository.TaskRepository.create_from_response"):
            r = client.post("/api/demo/process", json={"query": "X"}, headers=_headers())
            assert r.json()["success"] is True


class TestRoot:
    def test_ok(self, client):
        assert client.get("/").status_code == 200
