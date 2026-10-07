"""T3 评测工具单测（Linux 可跑的纯逻辑：oracle 求值 / 实例规划 / 判分 / 报告聚合）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval import load_tasks, validate_task  # noqa: E402
from eval.oracle_eval import eval_oracle, OracleEvaluationError  # noqa: E402
from eval import report as report_mod  # noqa: E402
import eval.run_eval as runner  # noqa: E402

TASKS_DIR = Path(__file__).resolve().parents[2] / "eval" / "tasks"


class FakeProbe:
    def __init__(self, files=None, texts=None, globs=None, windows=None,
                 elements=None, regs=None, clip=""):
        self.files = files or set()
        self.texts = texts or {}
        self.globs = globs or {}
        self.windows = windows or []
        self.elements = elements or []
        self.regs = regs or {}
        self.clip = clip

    def file_exists(self, p):
        return p in self.files

    def read_text(self, p):
        return self.texts.get(p)

    def glob_count(self, g):
        return self.globs.get(g, 0)

    def reg_value(self, hive, key, name):
        return self.regs.get(f"{hive}\\{key}\\{name}")

    def clipboard(self):
        return self.clip

    def window_titles(self):
        return self.windows

    def element_names(self, window_title_contains=None, element_type=None):
        out = self.elements
        if window_title_contains:
            out = [e for e in out if window_title_contains in e.get("w", "")]
        return [e["n"] for e in out]


def test_file_oracles():
    p = FakeProbe(files={"a.txt"}, texts={"a.txt": "hello HAJIMI_7 world"},
                  globs={"dir/*.txt": 3})
    ok, _ = eval_oracle({"all": [{"type": "file_exists", "path": "a.txt"}]}, p)
    assert ok
    ok, _ = eval_oracle(
        {"all": [{"type": "file_content_contains", "path": "a.txt", "needle": "HAJIMI_7"}]}, p)
    assert ok
    ok, _ = eval_oracle(
        {"all": [{"type": "file_content_contains", "path": "a.txt", "needle": "NOPE"}]}, p)
    assert not ok
    ok, _ = eval_oracle({"all": [{"type": "file_not_exists", "path": "b.txt"}]}, p)
    assert ok
    ok, _ = eval_oracle({"all": [{"type": "file_glob_min_count", "glob": "dir/*.txt", "min": 2}]}, p)
    assert ok
    ok, _ = eval_oracle({"all": [{"type": "file_glob_min_count", "glob": "dir/*.txt", "min": 9}]}, p)
    assert not ok


def test_window_and_element_oracles():
    p = FakeProbe(windows=["无标题 - 记事本", "设置"],
                  elements=[{"n": "缩放和布局", "w": "设置"}])
    ok, _ = eval_oracle({"all": [{"type": "uia_window_title_contains", "needle": "记事本"}]}, p)
    assert ok
    ok, _ = eval_oracle({"all": [{"type": "uia_window_not_exists", "needle": "字体"}]}, p)
    assert ok
    ok, _ = eval_oracle(
        {"any": [{"type": "uia_element_exists", "name_contains": "缩放",
                  "window_title_contains": "设置"}]}, p)
    assert ok
    ok, _ = eval_oracle({"any": [{"type": "uia_element_exists", "name_contains": "不存在"}]}, p)
    assert not ok


def test_all_and_any_combination():
    p = FakeProbe(files={"x"}, windows=["W1"])
    ok, trace = eval_oracle(
        {"all": [{"type": "file_exists", "path": "x"}],
         "any": [{"type": "uia_window_title_contains", "needle": "ZZZ"},
                 {"type": "uia_window_title_contains", "needle": "w1"}]},  # 大小写不敏感
        p,
    )
    assert ok and len(trace) == 3


def test_unknown_type_raises():
    import pytest

    with pytest.raises(OracleEvaluationError):
        eval_oracle({"all": [{"type": "mind_reader"}]}, FakeProbe())


def test_judge_semantics():
    assert runner.judge(True, "success", "success")
    assert not runner.judge(True, "fail", "success")
    # 负向任务：正确放弃 + oracle(现场保护)为真 → pass
    assert runner.judge(True, "fail", "fail")
    assert not runner.judge(False, "fail", "fail")  # 放弃但把现场弄坏=不通过


def test_plan_instances_expands_and_deterministic():
    tasks = load_tasks(TASKS_DIR)
    a = runner.plan_instances(tasks, repeats=4, order_seed=7)
    b = runner.plan_instances(tasks, repeats=4, order_seed=7)
    assert [x["instance_id"] for x in a] == [x["instance_id"] for x in b]
    expected_total = sum(len(t.seeds) * 4 for t in tasks)
    assert len(a) == expected_total
    # 每实例的 instruction 已代入 seed
    inst = next(x for x in a if x["instance_id"].startswith("notepad_type_save#b"))
    assert "HAJIMI_b_OK" in inst["task"].instruction


def test_expand_macros():
    obj = {"a": "{EVAL_DIR}/x", "b": ["{EVAL_DIR}/y", "keep"], "c": {"d": "{EVAL_DIR}/z"}}
    out = runner.expand_macros(obj, "C:\\ev")
    assert out["a"] == "C:\\ev/x" and out["b"][0] == "C:\\ev/y" and out["c"]["d"] == "C:\\ev/z"


def test_classify_failure_categories():
    assert runner.classify_failure("success", True, None, False) is None
    assert "timeout" in runner.classify_failure("fail", False, None, True)
    assert "卡死" in runner.classify_failure(
        "fail", False, {"loops": {"repeat5": 2}, "errors": {}, "snapshots": 3}, False)
    assert "grounding" in runner.classify_failure(
        "fail", False, {"loops": {}, "errors": {"element_not_found": 5}, "snapshots": 2}, False)
    assert "recovery" in runner.classify_failure(
        "fail", False, {"loops": {}, "errors": {}, "snapshots": 4}, False)


def test_summarize_tel_from_engine_shape():
    row = {"task_id": "t", "steps": [
        {"idx": 1, "status": "done", "tel": {
            "llm_calls": 5, "tokens_prompt": 4000, "tokens_completion": 120,
            "rounds": 5,
            "loop_events": {"repeat5": 1, "repeat8": 0},
            "gates": {"done_refused": 1, "failed_refused": 0, "unverified_done": 0},
            "expect": {"used": 2, "hit": 1},
            "errors": {"element_not_found": 1},
            "not_actionable": 1,
            "snapshots": {"count": 2, "latency_ms": [300, 500], "nodes": 40},
        }},
        {"idx": 2, "status": "failed", "tel": None},
    ]}
    s = runner.summarize_tel(row)
    assert s["llm_calls"] == 5 and s["tokens"] == 4120
    assert s["loops"]["repeat5"] == 1
    assert s["gates"]["done_refused"] == 1
    assert s["expect_used"] == 2 and s["expect_hit"] == 1
    assert s["not_actionable"] == 1 and s["snapshots"] == 2


def test_report_aggregation_and_markdown():
    results = [
        {"task_id": "t1", "seed": "a", "rep": 0, "pass": True, "wall_s": 10,
         "tel": {"llm_calls": 3, "tokens": 900, "rounds": 3, "loops": {}, "gates": {},
                 "errors": {}, "expect_used": 0, "expect_hit": 0,
                 "not_actionable": 0, "snapshots": 1}},
        {"task_id": "t1", "seed": "a", "rep": 1, "pass": False, "wall_s": 30,
         "category_fail": "recovery(执行偏航)",
         "tel": {"llm_calls": 6, "tokens": 2000, "rounds": 6, "loops": {"repeat5": 1},
                 "gates": {"done_refused": 1}, "errors": {"name_mismatch": 2},
                 "expect_used": 1, "expect_hit": 0, "not_actionable": 0, "snapshots": 2}},
        {"task_id": "t2", "seed": "a", "rep": 0, "pass": True, "wall_s": 8, "tel": None},
    ]
    agg = report_mod.aggregate(results)
    g = agg["global"]
    assert g["instances"] == 3
    assert abs(g["pass_at_1"] - (2 / 3)) < 1e-9
    assert agg["per_task"]["t1"]["all_pass_rate"] == 0.0
    assert agg["per_task"]["t2"]["all_pass_rate"] == 1.0
    assert g["fail_categories"]["recovery(执行偏航)"] == 1
    assert g["p0_behavior"]["gates"]["done_refused"] == 1
    assert g["p0_behavior"]["errors"]["name_mismatch"] == 2

    md = report_mod.render_markdown(agg, agg, "base", "new")
    assert "All-Pass 率(主)" in md and "| t1 |" in md

    md_single = report_mod.render_markdown(agg, None, "only")
    assert "逐任务" in md_single
