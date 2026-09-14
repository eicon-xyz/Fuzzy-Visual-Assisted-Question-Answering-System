"""评测失败归因分析器（T8）—— 把评测结果转成可执行的优化建议。

输入：eval_results/<label>.jsonl（run_eval 产物，含 pass/final_status/category_fail/tel）
输出：
  * defects.jsonl —— 每条失败实例一张缺陷票（含归因类别+证据+建议优化项）
  * 终端摘要 —— 失败模式聚合 + 建议优先级

映射表（对齐调研报告 §四 P1/P2）：
  grounding → 0.1 感知投影 / 0.3 id×name / A3 语义过滤
  perceptual → A2 多窗口 / A3 下钻 / 0.8 actionability
  progress-perception → 0.4 卡死检测 / P1-1.1 stall 账本
  recovery → P1-1.2 proactive replan / P2-2.1 宏库
  environment → 机器问题（锁屏/弹窗/网络），非代码
纯逻辑、Linux 可测；不做任何 LLM 调用。
"""
from __future__ import annotations

import json
from pathlib import Path

# 失败类别 → 建议优化项（含验证手段与对应报告条目）
CATEGORY_ADVICE = {
    "grounding": {
        "advice": "选错/选不到控件：优先验证 A3 语义过滤（词法 top-k）与 0.1 投影",
        "verify": "观察 errors.element_not_found/name_mismatch 是否在 filter 生效后下降",
        "report_ref": "§四 P0-0.1/0.3, P0.5 批次 A3",
    },
    "perceptual": {
        "advice": "看不见关键状态：优先验证 A2 多窗口感知与 A3 按需下钻",
        "verify": "观察 snapshots 延迟与 not_actionable 分布是否改善",
        "report_ref": "§四 P0-0.8, P0.5 批次 A2/A3",
    },
    "progress-perception": {
        "advice": "卡死不自知：优先 P1-1.1 stall 账本（清历史强制重规划）",
        "verify": "观察 loops.repeat5/8/12 后行为是否改变（nudge 后仍失败=检测只说话不拔电）",
        "report_ref": "§四 P1-1.1, 审查台账 E1/E2",
    },
    "recovery": {
        "advice": "执行偏航不恢复：优先 P1-1.2 proactive replan",
        "verify": "失败步数 > 3 且 errors 无 grounding/perceptual 特征时命中此档",
        "report_ref": "§四 P1-1.2, 审查台账 E1",
    },
    "environment": {
        "advice": "环境/超时类：先修机器（锁屏/弹窗/网络），不改代码",
        "verify": "cancelled=true 或 wall_s 逼近 max_wall_s",
        "report_ref": "评测台 HOWTO §6",
    },
}


def analyze(results: list, runs_path=None) -> dict:
    """聚合评测结果 → {defects, by_category, advice, counts}。"""
    defects = []
    by_category = {}
    for r in results:
        if r.get("pass"):
            continue
        cat = r.get("category_fail") or "unknown"
        # 规范化：去掉括号细节与子类别，如 "recovery(执行偏航)"→"recovery"、
        # "environment/timeout"→"environment"
        base_cat = cat.split("(")[0].split("/")[0]
        by_category.setdefault(base_cat, []).append(r)
        advice = CATEGORY_ADVICE.get(base_cat, {
            "advice": f"未识别类别 {cat}：人工核查",
            "verify": "见缺陷票原始字段",
            "report_ref": "—",
        })
        defects.append({
            "instance_id": r.get("instance_id"),
            "task_id": r.get("task_id"),
            "seed": r.get("seed"),
            "rep": r.get("rep"),
            "label": r.get("label"),
            "category": cat,
            "final_status": r.get("final_status"),
            "wall_s": r.get("wall_s"),
            "errors": (r.get("tel") or {}).get("errors", {}),
            "loops": (r.get("tel") or {}).get("loops", {}),
            "advice": advice["advice"],
            "verify": advice["verify"],
            "report_ref": advice["report_ref"],
        })
    counts = {k: len(v) for k, v in by_category.items()}
    # 优先级：占比最高的类别排第一
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    priority = []
    for cat, n in ranked:
        advice = CATEGORY_ADVICE.get(cat, {})
        priority.append({"category": cat, "count": n,
                         "advice": advice.get("advice", "人工核查")})
    return {"defects": defects, "by_category": counts,
            "priority": priority, "total_failures": len(defects)}


def write_defects(agg: dict, out_fp: Path) -> int:
    """缺陷票追加写 defects.jsonl，返回票数。"""
    out_fp.parent.mkdir(parents=True, exist_ok=True)
    with open(out_fp, "a", encoding="utf-8") as f:
        for d in agg["defects"]:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return len(agg["defects"])


def load_results(fp) -> list:
    out = []
    for line in Path(fp).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def main(argv=None):
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("用法: fail_analyzer.py <results.jsonl> <defects_out.jsonl>")
        return 1
    results = load_results(argv[0])
    agg = analyze(results)
    n = write_defects(agg, Path(argv[1]))
    print(f"缺陷票 {n} 张 → {argv[1]}")
    for p in agg["priority"]:
        print(f"  [{p['count']:2d}] {p['category']}: {p['advice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
