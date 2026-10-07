"""T8 fail_analyzer 单元测试——合成评测结果驱动，断言归因/建议/缺陷票。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from eval import fail_analyzer as fa  # noqa: E402


def _rec(task, cat, pass_=False, tel=None, **kw):
    r = {"instance_id": f"{task}#a#0", "task_id": task, "seed": "a", "rep": 0,
         "label": "test", "pass": pass_, "category_fail": cat,
         "final_status": "fail", "wall_s": 30, "tel": tel or {}}
    r.update(kw)
    return r


def test_grounding_defect_advice():
    agg = fa.analyze([
        _rec("t1", "grounding(选错/选不到控件)",
             tel={"errors": {"element_not_found": 3, "name_mismatch": 1}}),
    ])
    assert agg["total_failures"] == 1
    d = agg["defects"][0]
    assert "A3" in d["advice"] and "0.1" in d["advice"]
    assert d["errors"]["element_not_found"] == 3


def test_category_grouping_and_priority():
    agg = fa.analyze([
        _rec("t1", "grounding(x)"),
        _rec("t2", "grounding(y)"),
        _rec("t3", "recovery(执行偏航)"),
        _rec("t4", "environment/timeout", cancelled=True),
    ])
    assert agg["by_category"] == {"grounding": 2, "recovery": 1, "environment": 1}
    # 优先级按数量降序
    assert agg["priority"][0]["category"] == "grounding"
    assert agg["priority"][0]["count"] == 2


def test_progress_advice_points_to_stall_ledger():
    agg = fa.analyze([
        _rec("t1", "progress-perception(卡死)",
             tel={"loops": {"repeat5": 2, "repeat8": 1}, "errors": {}}),
    ])
    d = agg["defects"][0]
    assert "P1-1.1" in d["advice"]
    assert d["loops"]["repeat5"] == 2


def test_passed_instances_excluded():
    agg = fa.analyze([
        _rec("t1", "grounding(x)", pass_=True),
        _rec("t2", "recovery(y)"),
    ])
    assert agg["total_failures"] == 1
    assert agg["defects"][0]["task_id"] == "t2"


def test_unknown_category_falls_back_to_manual():
    agg = fa.analyze([_rec("t1", "mystery-category")])
    assert "人工核查" in agg["defects"][0]["advice"]


def test_write_defects_appends_jsonl(tmp_path):
    agg = fa.analyze([_rec("t1", "recovery(x)"), _rec("t2", "grounding(y)")])
    fp = tmp_path / "defects.jsonl"
    n = fa.write_defects(agg, fp)
    assert n == 2
    lines = [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert lines[0]["task_id"] == "t1"
    assert "report_ref" in lines[0]


def test_load_results_skips_bad_lines(tmp_path):
    fp = tmp_path / "r.jsonl"
    fp.write_text('{"pass": true}\nnot json\n{"pass": false, "category_fail": "recovery(x)"}\n',
                  encoding="utf-8")
    results = fa.load_results(fp)
    assert len(results) == 2


def test_cli_smoke(tmp_path):
    inp = tmp_path / "in.jsonl"
    inp.write_text(json.dumps(_rec("t1", "grounding(x)")) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    rc = fa.main([str(inp), str(out)])
    assert rc == 0 and out.exists()
