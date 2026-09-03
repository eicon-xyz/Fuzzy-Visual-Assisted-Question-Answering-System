"""T1 评测遥测单测：tally 纯函数 / _LoopDetector 越界事件 / execute_step 记账 /
engine JSONL 落盘 / R1 截图不进 LLM 上下文 / 遥测故障不影响执行链。"""
from __future__ import annotations

import json

import pytest

import test_executor_p0 as tp  # 复用桩与 fake（同目录）
from server.models.schemas import ExecutedStep
from server.services import eval_telemetry as et
from server.services.executor import agent as agent_mod


# ── 纯函数 ──────────────────────────────────────────────────────────────


def test_tally_tool_counts_everything():
    tel = et.new_step_telemetry()
    et.tally_tool(tel, "click", {"ok": True, "expect_ok": False, "expect_detail": {}}, 120)
    assert tel["tool_calls"]["click"] == 1
    assert tel["expect"] == {"used": 1, "hit": 0}
    assert tel["slowest_ms"]["click"] == 120

    et.tally_tool(tel, "click", {"ok": True, "expect_ok": True}, 50)
    assert tel["expect"] == {"used": 2, "hit": 1}
    assert tel["slowest_ms"]["click"] == 120  # 取最大值

    et.tally_tool(
        tel, "mark_step_done",
        {"ok": False, "error_code": "done_without_evidence"}, 1,
    )
    assert tel["gates"]["done_refused"] == 1
    assert tel["errors"]["done_without_evidence"] == 1

    et.tally_tool(tel, "click", {"ok": False, "error_code": "not_actionable"}, 3000)
    assert tel["not_actionable"] == 1
    assert tel["errors"]["not_actionable"] == 1

    et.tally_tool(tel, "wait", {"ok": True}, 2000)
    assert tel["slowest_ms"]["wait"] == 2000

    # None 安全
    et.tally_tool(None, "click", {"ok": True})


def test_snapshot_tally():
    tel = et.new_step_telemetry()
    et.tally_snapshot(tel, 123.7, 40)
    et.tally_snapshot(tel, 55, 17)
    assert tel["snapshots"]["count"] == 2
    assert tel["snapshots"]["latency_ms"] == [123, 55]
    assert tel["snapshots"]["nodes"] == 40


def test_llm_usage_tally():
    tel = et.new_step_telemetry()
    et.tally_llm_usage(tel, {"prompt_tokens": 900, "completion_tokens": 40})
    et.tally_llm_usage(tel, {"prompt_tokens": 1000, "completion_tokens": 60})
    assert tel["llm_calls"] == 2
    assert tel["tokens_prompt"] == 1900
    assert tel["tokens_completion"] == 100


# ── _LoopDetector 越界事件 ──────────────────────────────────────────────


def test_loop_detector_events_count_crossings():
    ev = {"repeat5": 0, "repeat8": 0, "repeat12": 0, "stagnation": 0, "replan": 0}
    d = agent_mod._LoopDetector(ev)
    for _ in range(12):
        d.record_action("click", {"element_id": "u1"}, True)
        d.build_nudge()
    assert ev["repeat5"] == 1 and ev["repeat8"] == 1 and ev["repeat12"] == 1
    # 停留在 12 档不再重复计数
    d.record_action("click", {"element_id": "u1"}, True)
    d.build_nudge()
    assert ev["repeat12"] == 1
    # 换动作回落后再次越过 5 档 → 再计一次
    d.record_action("click", {"element_id": "u2"}, True)
    for _ in range(5):
        d.record_action("click", {"element_id": "u1"}, True)
        d.build_nudge()
    assert ev["repeat5"] == 2


def test_loop_detector_stagnation_event_once():
    ev = {"repeat5": 0, "repeat8": 0, "repeat12": 0, "stagnation": 0, "replan": 0}
    d = agent_mod._LoopDetector(ev)
    snap = [{"type": "button", "name": "x", "bbox": [0, 0, 1, 1]}]
    for _ in range(7):
        d.record_observation(snap)
        d.build_nudge()
    assert ev["stagnation"] == 1


# ── execute_step 集成：步遥测生成 ───────────────────────────────────────


def test_execute_step_populates_step_tel(monkeypatch):
    a = tp._scripted_agent(monkeypatch, [
        ("click", {"element_id": "u1", "name": "确定"}),
        ("mark_step_done", {"reason": "ok", "evidence": ""}),
    ])
    result = a.execute_step(tp._step(), goal="g", previous_steps=[])
    assert result.status == "done"
    tel = a._step_tel
    assert tel["tool_calls"]["click"] == 1
    assert tel["tool_calls"]["mark_step_done"] == 1
    assert tel["gates"]["done_refused"] == 0  # 有 state_changed 强证据，一次放行
    assert "click" in tel["slowest_ms"]


def test_r1_annotated_image_never_enters_llm_messages(monkeypatch):
    """截图只走 SSE 回调；tool message 里不得出现 annotated_image/base64。"""
    a = tp._make_agent_with_fake_bridge(tp._click_ok_bridge())
    seq = [
        ("get_screen_info", {}),
        ("mark_step_done", {"reason": "r", "evidence": "窗口标题含'无标题 - 记事本'"}),
    ]
    idx = [0]
    captured = []

    def fake_llm(msgs):
        captured.append(json.dumps(msgs, ensure_ascii=False))
        i = min(idx[0], len(seq) - 1)
        idx[0] += 1
        name, args = seq[i]
        return json.dumps({"__tool_call__": True, "name": name, "arguments": args}), None

    monkeypatch.setattr(a, "_call_llm_with_tools", fake_llm)
    monkeypatch.setattr(agent_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(a, "clear_element_map", lambda: None)

    def _no_mem():
        raise RuntimeError

    monkeypatch.setattr(agent_mod, "get_retriever", _no_mem)
    monkeypatch.setattr(
        a, "_do_get_screen_info",
        lambda: {
            "success": True, "elements": [], "element_count": 0,
            "annotated_image": "data:image/jpeg;base64,BIGBLOB",
            "action_summary": "obs",
        },
    )
    shots = []
    result = a.execute_step(
        tp._step(), goal="g", previous_steps=[], on_screenshot=shots.append,
    )
    assert result.status == "done"
    assert shots == ["data:image/jpeg;base64,BIGBLOB"]  # B 端截图链路保留
    assert len(captured) >= 2  # 至少发生过第二轮 LLM 调用（能看到 tool message）
    for snapshot_msgs in captured[1:]:
        assert "BIGBLOB" not in snapshot_msgs


# ── engine 集成：JSONL 落盘与故障免疫 ───────────────────────────────────


def test_engine_writes_runs_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("HAJIMI_EVAL_DIR", str(tmp_path))
    from server.services.executor import engine

    q = engine.register_task("t-eval-1")

    def fake_execute_step(self, step, goal, previous_steps, **kw):
        self._step_tel = et.new_step_telemetry()
        et.tally_tool(self._step_tel, "click", {"ok": True}, 10)
        step.status = "done"
        step.action_summary = "ok"
        step.evidence = "click→确定 state_changed=True"
        return step

    import server.services.executor.agent as ag_mod

    monkeypatch.setattr(ag_mod.ExecutionAgent, "execute_step", fake_execute_step)
    monkeypatch.setattr(ag_mod.ExecutionAgent, "close_browser", lambda self: None)
    monkeypatch.setattr(engine, "_trigger_memory_extraction_success", lambda *a, **k: None)
    import threading as _th

    engine.run_plan_agent_loop(
        "t-eval-1", "打开记事本并输入", [{"step_index": 1, "instruction": "打开"}],
        _th.Event(),
    )
    while not q.empty():
        q.get()
    line_path = tmp_path / "runs.jsonl"
    assert line_path.exists()
    rec = json.loads(line_path.read_text(encoding="utf-8").strip())
    assert rec["task_id"] == "t-eval-1"
    assert rec["final_status"] == "success"
    assert rec["steps"][0]["status"] == "done"
    assert rec["steps"][0]["tel"]["tool_calls"]["click"] == 1
    assert "git_sha" in rec and "wall_ms" in rec
    engine.unregister_task("t-eval-1")


def test_engine_survives_telemetry_failure(tmp_path, monkeypatch):
    """record_task 抛异常不得影响任务执行链。"""
    from server.services.executor import engine
    import server.services.executor.agent as ag_mod

    q = engine.register_task("t-eval-2")

    def fake_execute_step(self, step, goal, previous_steps, **kw):
        step.status = "done"
        step.action_summary = "ok"
        return step

    monkeypatch.setattr(ag_mod.ExecutionAgent, "execute_step", fake_execute_step)
    monkeypatch.setattr(ag_mod.ExecutionAgent, "close_browser", lambda self: None)
    monkeypatch.setattr(engine, "_trigger_memory_extraction_success", lambda *a, **k: None)
    monkeypatch.setattr(
        et, "record_task",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("disk on fire")),
    )
    import threading as _th

    engine.run_plan_agent_loop(  # 不应抛出
        "t-eval-2", "g", [{"step_index": 1, "instruction": "x"}], _th.Event(),
    )
    names = []
    while not q.empty():
        names.append(q.get()["event"])
    assert "task_done" in names
    engine.unregister_task("t-eval-2")


def test_engine_crash_guard_records_failure(tmp_path, monkeypatch):
    """引擎内核线程级崩溃（如依赖 import 失败）→ task_failed 事件 + fail 遥测记录。"""
    from server.services.executor import engine
    import threading as _th

    monkeypatch.setenv("HAJIMI_EVAL_DIR", str(tmp_path))
    q = engine.register_task("t-crash")
    monkeypatch.setattr(
        engine, "_run_plan_agent_loop",
        lambda *a, **k: (_ for _ in ()).throw(ImportError("No module named 'pyautogui'")),
    )
    engine.run_plan_agent_loop(
        "t-crash", "g", [{"step_index": 1, "instruction": "x"}], _th.Event(),
    )
    events = []
    while not q.empty():
        events.append(q.get())
    failed = [e for e in events if e["event"] == "task_failed"]
    assert failed and "pyautogui" in failed[0]["data"]["reason"]
    rec = json.loads((tmp_path / "runs.jsonl").read_text(encoding="utf-8").strip())
    assert rec["final_status"] == "fail"
    engine.unregister_task("t-crash")
