"""T2 评测任务集校验测试（Linux 可跑：纯 schema/loader/coverage 逻辑）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # server_A/

from eval import (  # noqa: E402
    P0_ITEMS,
    TaskValidationError,
    coverage_report,
    load_tasks,
    validate_task,
)

TASKS_DIR = Path(__file__).resolve().parents[2] / "eval" / "tasks"


def _minimal(**over):
    base = {
        "id": "t_x",
        "name": "x",
        "category": "editor",
        "instruction": "open notepad",
        "seeds": ["a"],
        "p0_coverage": ["0.1"],
        "oracle": {"all": [{"type": "file_exists", "path": "/tmp/x"}]},
    }
    base.update(over)
    return base


def test_seed_tasks_all_valid():
    tasks = load_tasks(TASKS_DIR)
    assert len(tasks) >= 16, "首批至少 16 条"
    ids = [t.id for t in tasks]
    assert len(ids) == len(set(ids))


def test_every_p0_item_has_two_tasks():
    cr = coverage_report(load_tasks(TASKS_DIR))
    assert cr["undercovered"] == {}, f"P0 暴露缺口: {cr['undercovered']}"


def test_seed_tasks_ship_uncalibrated():
    """诚实检查：新加入的任务默认 calibrated=false，校准是显式动作。"""
    tasks = load_tasks(TASKS_DIR)
    assert all(isinstance(t.calibrated, bool) for t in tasks)


def test_negative_tasks_exist():
    tasks = load_tasks(TASKS_DIR)
    neg = [t for t in tasks if t.expect_status == "fail"]
    assert len(neg) >= 2


def test_render_replaces_nested_and_preserves_macro():
    t = validate_task(_minimal(instruction="save {EVAL_DIR}/f_{seed}.txt")).render("s1")
    assert t.instruction == "save {EVAL_DIR}/f_s1.txt"  # 宏保留给 runner 展开
    assert t.oracle["all"][0]["path"] == "/tmp/x"
    t2 = validate_task(
        _minimal(oracle={"all": [{"type": "file_content_contains", "path": "p", "needle": "n_{seed}"}]})
    ).render("z")
    assert t2.oracle["all"][0]["needle"] == "n_z"  # 嵌套 dict 里的值也替换


def test_bad_oracle_type_rejected():
    with pytest.raises(TaskValidationError, match="未知 oracle 类型"):
        validate_task(_minimal(oracle={"all": [{"type": "telepathy"}]}))


def test_llm_judge_oracle_banned():
    with pytest.raises(TaskValidationError, match="非确定性"):
        validate_task(_minimal(oracle={"all": [{"type": "screenshot_match"}]}))


def test_oracle_requires_all_or_any():
    with pytest.raises(TaskValidationError, match="all 或 any"):
        validate_task(_minimal(oracle={"foo": []}))


def test_oracle_missing_field_rejected():
    with pytest.raises(TaskValidationError, match="缺字段"):
        validate_task(_minimal(oracle={"all": [{"type": "file_content_contains", "path": "p"}]}))


def test_unknown_category_and_status_rejected():
    with pytest.raises(TaskValidationError, match="category"):
        validate_task(_minimal(category="quantum"))
    with pytest.raises(TaskValidationError, match="expect_status"):
        validate_task(_minimal(expect_status="maybe"))


def test_unknown_p0_coverage_rejected():
    with pytest.raises(TaskValidationError, match="p0_coverage"):
        validate_task(_minimal(p0_coverage=["9.9"]))


def test_dupe_ids_across_files_rejected(tmp_path):
    import json

    (tmp_path / "a.json").write_text(json.dumps([_minimal()]), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps([_minimal(name="dup")]), encoding="utf-8")
    with pytest.raises(TaskValidationError, match="重复任务 id"):
        load_tasks(tmp_path)
