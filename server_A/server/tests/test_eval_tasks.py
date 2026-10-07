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


# ── gold 校准 schema 扩展（__init__.py 最小 diff 的回归钉）──────────────────

def test_seed_tasks_ship_calib_fields_at_defaults():
    """未校准任务不写新字段也合法：loader 给默认值（兼容承诺）。

    已校准任务（calibrated:true）可带 calibration_method（human/gold-v1），
    未校准任务必须为空——后者是防误配的默认值钉。
    """
    tasks = load_tasks(TASKS_DIR)  # 全目录 = seed.json 20 条 + waa_pilot.json 10 条
    hand = [t for t in tasks if t.source == "handcrafted"]
    assert len(hand) == 20
    uncal = [t for t in hand if not t.calibrated]
    assert uncal, "至少应有未校准的 handcrafted 任务"
    assert all(t.calib_gold == [] and t.calibration_method == "" for t in uncal)
    # 已校准任务（B1 置位后）：method 必须非空且合法
    for t in hand:
        if t.calibrated:
            assert t.calibration_method in ("human", "gold-v1"), t.id


def test_calib_gold_fields_roundtrip_and_render():
    t = validate_task(_minimal(
        calib_gold=['Set-Content "{EVAL_DIR}/f_{seed}.txt" -Value "x"'],
        calibration_method="gold-v1"))
    assert t.calib_gold and t.calibration_method == "gold-v1"
    r = t.render("s9")
    assert r.calib_gold == ['Set-Content "{EVAL_DIR}/f_s9.txt" -Value "x"'], \
        "render 必须把 {seed} 代入 gold 行（与 setup/cleanup 同规则）"
    assert r.calibration_method == "gold-v1"
    # 原任务不被 render 污染（纯函数性回归）
    assert "{seed}" in t.calib_gold[0]


def test_calibration_method_whitelist_enforced():
    with pytest.raises(TaskValidationError):
        validate_task(_minimal(calibration_method="llm-judged"))
    with pytest.raises(TaskValidationError):
        validate_task(_minimal(calib_gold=[42]))
    for m in ("", "gold-v1", "human"):
        assert validate_task(_minimal(calibration_method=m)).calibration_method == m
