"""T7 SSE 事件契约测试——驱动真实 engine 事件流，断言 P0 新增字段。

直接调用 engine.run_plan_agent_loop + fake agent（不进真实 LLM/浏览器），
消费注册队列断言事件顺序与字段契约。覆盖：
  step_start / step_done(evidence) / step_failed / step_blocked(question) /
  tool_called / tool_result(error_code+hint) / task_done / task_failed
"""
from __future__ import annotations

import threading

import pytest

from server.services.executor import engine
import server.services.executor.agent as agent_mod


@pytest.fixture(autouse=True)
def _clean_queue(monkeypatch, tmp_path):
    monkeypatch.setenv("HAJIMI_EVAL_DIR", str(tmp_path))
    engine._event_queues.clear()
    engine._cancel_flags.clear()
    engine._cancel_events.clear()
    yield
    engine._event_queues.clear()
    engine._cancel_flags.clear()
    engine._cancel_events.clear()


def _drain(q):
    events = []
    while not q.empty():
        events.append(q.get())
    return events


class _FakeDoneAgent:
    """execute_step 直接返回 done，带证据。"""

    def execute_step(self, step, goal, previous_steps, **kw):
        step.status = "done"
        step.action_summary = "打开成功"
        step.evidence = "click→记事本 state_changed=True verified=True"
        return step

    def close_browser(self):
        pass


class _FakeAskAgent:
    def execute_step(self, step, goal, previous_steps, **kw):
        step.status = "failed"
        step.terminal_kind = "ask_user"
        step.user_question = "需要登录，账号密码？"
        step.action_summary = "[需用户决策] 需要登录，账号密码？"
        return step

    def close_browser(self):
        pass


class _FakeToolAgent:
    """首轮工具调用返回后第二轮 done——产生 tool_called/tool_result 事件。"""

    def __init__(self, step_tel=None):
        self.calls = 0
        self._step_tel = step_tel

    def execute_step(self, step, goal, previous_steps, **kw):
        on_tool = kw.get("on_tool_event")
        if on_tool and self.calls == 0:
            on_tool("tool_called", {"tool": "click", "args": {"element_id": "u1"}})
            on_tool("tool_result", {
                "tool": "click", "success": True,
                "action_summary": "clicked", "duration_ms": 12,
                "error": None, "error_code": None, "hint": None,
            })
            self.calls += 1
        step.status = "done"
        step.action_summary = "ok"
        step.evidence = "uia_expand 展开后选择"
        return step

    def close_browser(self):
        pass


def _run(task_id, steps, agent, monkeypatch):
    monkeypatch.setattr(agent_mod.ExecutionAgent, "execute_step", agent.execute_step)
    monkeypatch.setattr(agent_mod.ExecutionAgent, "close_browser", agent.close_browser)
    monkeypatch.setattr(engine, "_trigger_memory_extraction_success", lambda *a, **k: None)
    q = engine.register_task(task_id)
    engine.run_plan_agent_loop(task_id, "目标", steps, threading.Event())
    return _drain(q)


def test_step_done_event_carries_evidence(monkeypatch):
    evs = _run("sse-1", [{"step_index": 1, "instruction": "打开记事本"}],
               _FakeDoneAgent(), monkeypatch)
    done = [e for e in evs if e["event"] == "step_done"]
    assert len(done) == 1
    assert done[0]["data"]["step_index"] == 1
    # P0-0.7 契约：done 必须带 evidence
    assert "evidence" in done[0]["data"]
    assert "state_changed" in done[0]["data"]["evidence"]
    assert [e["event"] for e in evs].count("task_done") == 1


def test_ask_user_emits_step_blocked_with_question(monkeypatch):
    evs = _run("sse-2", [{"step_index": 1, "instruction": "登录"}],
               _FakeAskAgent(), monkeypatch)
    blocked = [e for e in evs if e["event"] == "step_blocked"]
    assert len(blocked) == 1
    assert blocked[0]["data"]["question"] == "需要登录，账号密码？"
    # P0-0.7 契约：ask_user 不重试、不产生 step_done
    assert not [e for e in evs if e["event"] == "step_done"]
    assert [e for e in evs if e["event"] == "task_failed"]


def test_tool_events_carry_contract_fields(monkeypatch):
    evs = _run("sse-3", [{"step_index": 1, "instruction": "点按钮"}],
               _FakeToolAgent(), monkeypatch)
    called = [e for e in evs if e["event"] == "tool_called"]
    results = [e for e in evs if e["event"] == "tool_result"]
    assert called and called[0]["data"]["tool"] == "click"
    # P0-0.6 契约：tool_result 带 success/duration/error_code/hint
    r = results[0]["data"]
    assert r["success"] is True and r["duration_ms"] == 12
    assert "error_code" in r and "hint" in r


def test_step_failed_contract(monkeypatch):
    class _FailAgent(_FakeDoneAgent):
        def execute_step(self, step, goal, previous_steps, **kw):
            step.status = "failed"
            step.action_summary = "element not found"
            return step

    evs = _run("sse-4", [{"step_index": 1, "instruction": "点击不存在"}],
               _FailAgent(), monkeypatch)
    failed = [e for e in evs if e["event"] == "step_failed"]
    assert failed and failed[0]["data"]["reason"] == "element not found"
    assert [e for e in evs if e["event"] == "task_done"] == []


def test_event_order_start_before_done(monkeypatch):
    evs = _run("sse-5", [{"step_index": 1, "instruction": "x"}],
               _FakeDoneAgent(), monkeypatch)
    order = [e["event"] for e in evs if e["event"] in ("step_start", "step_done")]
    assert order == ["step_start", "step_done"]


def test_task_done_payload_counts(monkeypatch):
    evs = _run("sse-6", [
        {"step_index": 1, "instruction": "a"},
        {"step_index": 2, "instruction": "b"},
    ], _FakeDoneAgent(), monkeypatch)
    done = [e for e in evs if e["event"] == "task_done"][0]
    assert done["data"]["total_steps"] == 2
    assert done["data"]["completed_steps"] == 2
