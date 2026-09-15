"""T6 planner.py 单元测试——mock call_llm，覆盖解析/回退/重试/失败路径。"""
from __future__ import annotations

import pytest

import server.services.planning.planner as planner


def test_plan_steps_normal_json(monkeypatch):
    monkeypatch.setattr(
        planner, "call_llm",
        lambda **k: '{"goal": "打开记事本", "steps": [{"step_index": 1, '
                    '"instruction": "打开记事本应用"}, {"step_index": 2, '
                    '"instruction": "输入hello"}]}',
    )
    r = planner.plan_steps("打开记事本输入hello")
    assert r.goal == "打开记事本"
    assert len(r.steps) == 2
    assert r.steps[0].instruction == "打开记事本应用"
    assert r.steps[0].step_index == 1


def test_plan_steps_string_steps(monkeypatch):
    """LLM 返回字符串数组步骤 → 按序编号。"""
    monkeypatch.setattr(
        planner, "call_llm",
        lambda **k: '{"goal": "g", "steps": ["打开应用", "输入内容"]}',
    )
    r = planner.plan_steps("q")
    assert [s.instruction for s in r.steps] == ["打开应用", "输入内容"]
    assert [s.step_index for s in r.steps] == [1, 2]


def test_plan_steps_empty_steps_fallback_to_query(monkeypatch):
    """steps 为空数组 → 单步=整句查询。"""
    monkeypatch.setattr(planner, "call_llm", lambda **k: '{"goal": "g", "steps": []}')
    r = planner.plan_steps("帮我打开记事本")
    assert len(r.steps) == 1
    assert r.steps[0].instruction == "帮我打开记事本"


def test_plan_steps_missing_goal_defaults(monkeypatch):
    """goal 缺失时 extract_json_object 兜底为 'Complete the task'（providers 层行为）。"""
    monkeypatch.setattr(
        planner, "call_llm",
        lambda **k: '{"steps": [{"instruction": "x"}]}',
    )
    r = planner.plan_steps("原查询")
    assert r.goal == "Complete the task"


def test_plan_steps_retry_then_success(monkeypatch):
    """第一次 LLM 返回坏 JSON，重试成功。"""
    calls = {"n": 0}

    def fake_llm(**k):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not json at all"
        return '{"goal": "g", "steps": [{"instruction": "ok"}]}'

    monkeypatch.setattr(planner, "call_llm", fake_llm)
    r = planner.plan_steps("q", max_retries=2)
    assert len(r.steps) == 1 and calls["n"] == 2


def test_plan_steps_all_retries_fail(monkeypatch):
    """全部重试失败 → ValueError（含最后一次的错误信息）。"""
    monkeypatch.setattr(planner, "call_llm", lambda **k: "garbage",)
    with pytest.raises(ValueError, match="Planning Agent failed"):
        planner.plan_steps("q", max_retries=1)


def test_plan_steps_steps_without_instruction(monkeypatch):
    """dict 步骤缺 instruction → 用 str(s) 兜底。"""
    monkeypatch.setattr(
        planner, "call_llm",
        lambda **k: '{"goal": "g", "steps": [{"foo": 1}]}',
    )
    r = planner.plan_steps("q")
    assert len(r.steps) == 1 and "foo" in r.steps[0].instruction
