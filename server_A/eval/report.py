"""评测报告器（T3）：结果 JSONL → pass@1 / All-Pass@N / 成本 / 失败四类 / P0 行为指标。

用法:
    python eval/report.py eval_results/base.jsonl [eval_results/new.jsonl]
        单文件 → 总览；双文件 → A/B 对比（约定：第一个是基线批次）。
口径（对齐报告 §四 2.4）：
  * 主指标 All-Pass@N：同任务同 seed 的 N 次重复全过才算稳定通过（生产可靠性）；
  * 辅指标 pass@1：单次通过率均值；
  * 未校准任务（oracle 从未人工两向验证）不应进正式口径——由调用方保证。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def load_results(fp):
    out = []
    for line in Path(fp).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _tel_get(rec, key):
    tel = rec.get("tel") or {}
    return tel.get(key, 0) or 0


def aggregate(results):
    """{per_task:{id:{...}}, global:{...}}"""
    by_task = defaultdict(lambda: defaultdict(list))  # task -> seed -> [rec]
    for r in results:
        by_task[r.get("task_id", "?")][r.get("seed", "?")].append(r)

    per_task = {}
    for tid, seeds in by_task.items():
        seed_stats = []
        for seed, recs in seeds.items():
            n = len(recs)
            passed = sum(1 for r in recs if r.get("pass"))
            seed_stats.append({"seed": seed, "n": n, "passed": passed,
                               "all_pass": passed == n})
        all_pass_n = sum(1 for s in seed_stats if s["all_pass"])
        pass1 = sum(s["passed"] / max(s["n"], 1) for s in seed_stats) / max(len(seed_stats), 1)
        per_task[tid] = {
            "seeds": len(seed_stats),
            "runs": sum(s["n"] for s in seed_stats),
            "all_pass_seeds": all_pass_n,
            "all_pass_rate": all_pass_n / max(len(seed_stats), 1),
            "pass_at_1": pass1,
        }

    n_all = len(results)
    def _mean(key):
        vals = [_tel_get(r, key) for r in results if r.get("tel")]
        return sum(vals) / len(vals) if vals else 0

    fail_cat = defaultdict(int)
    for r in results:
        if not r.get("pass") and r.get("category_fail"):
            fail_cat[r["category_fail"]] += 1

    gates = defaultdict(int)
    loops = defaultdict(int)
    errors = defaultdict(int)
    expect_used = expect_hit = na = snaps = 0
    for r in results:
        tel = r.get("tel") or {}
        for k, v in (tel.get("gates") or {}).items():
            gates[k] += v or 0
        for k, v in (tel.get("loops") or {}).items():
            loops[k] += v or 0
        for k, v in (tel.get("errors") or {}).items():
            errors[k] += v or 0
        expect_used += tel.get("expect_used", 0) or 0
        expect_hit += tel.get("expect_hit", 0) or 0
        na += tel.get("not_actionable", 0) or 0
        snaps += tel.get("snapshots", 0) or 0

    return {
        "per_task": per_task,
        "global": {
            "instances": n_all,
            "pass": sum(1 for r in results if r.get("pass")),
            "pass_at_1": sum(1 for r in results if r.get("pass")) / max(n_all, 1),
            "all_pass_rate": sum(t["all_pass_rate"] for t in per_task.values())
            / max(len(per_task), 1),
            "avg_llm_calls": _mean("llm_calls"),
            "avg_tokens": _mean("tokens"),
            "avg_rounds": _mean("rounds"),
            "avg_wall_s": sum(r.get("wall_s", 0) or 0 for r in results) / max(n_all, 1),
            "fail_categories": dict(fail_cat),
            "p0_behavior": {
                "expect_used": expect_used, "expect_hit": expect_hit,
                "gates": dict(gates), "loops": dict(loops),
                "errors": dict(errors), "not_actionable": na, "snapshots": snaps,
            },
        },
    }


def render_markdown(agg_a, agg_b=None, label_a="A", label_b="B"):
    L = []
    L.append("# HAJIMI L5 评测报告")
    if agg_b is None:
        L.append(f"\n## 总览 · {label_a}")
        L.append(_overview_md(label_a, agg_a["global"]))
        L.append(_tasks_md([(label_a, agg_a)]))
        L.append("\n> 口径：all_pass=该任务全部 seed 的 N 次重复皆过；"
                 "成本列为 tel 均值（runner 崩溃/无遥测实例不计入）。")
        return "\n".join(L)

    a, b = agg_a["global"], agg_b["global"]
    L.append(f"\n## 对比 · 基线({label_a}) → 现行({label_b})")
    L.append("")
    L.append("| 指标 | 基线 | 现行 | Δ |")
    L.append("|---|---|---|---|")
    rows = [
        ("All-Pass 率(主)", a["all_pass_rate"], b["all_pass_rate"], "pct"),
        ("pass@1", a["pass_at_1"], b["pass_at_1"], "pct"),
        ("均 LLM 调用/实例", a["avg_llm_calls"], b["avg_llm_calls"], "num"),
        ("均 tokens/实例", a["avg_tokens"], b["avg_tokens"], "num"),
        ("均轮次/实例", a["avg_rounds"], b["avg_rounds"], "num"),
        ("均耗时 s/实例", a["avg_wall_s"], b["avg_wall_s"], "num"),
    ]
    for name, va, vb, kind in rows:
        if kind == "pct":
            L.append(f"| {name} | {va:.1%} | {vb:.1%} | {vb-va:+.1%} |")
        else:
            d = vb - va
            pct = f" ({d / va:+.0%})" if va else ""
            L.append(f"| {name} | {va:.1f} | {vb:.1f} | {d:+.1f}{pct} |")
    L.append("")
    L.append(f"### 基线批次 {label_a}")
    L.append(_overview_md(label_a, a))
    L.append(f"\n### 现行批次 {label_b}")
    L.append(_overview_md(label_b, b))
    L.append(_tasks_md([(label_a, agg_a), (label_b, agg_b)]))
    return "\n".join(L)


def _overview_md(label, g):
    pb = g.get("p0_behavior", {})
    L = [f"- 实例 {g['instances']}，All-Pass 率 **{g['all_pass_rate']:.1%}**，"
         f"pass@1 {g['pass_at_1']:.1%}",
         f"- 成本：LLM {g['avg_llm_calls']:.1f} 次 / {g['avg_tokens']:.0f} tokens / "
         f"{g['avg_rounds']:.1f} 轮 / {g['avg_wall_s']:.0f}s（每实例均值）",
         f"- 失败四类：{g['fail_categories'] or '—'}",
         f"- P0 行为：expect {pb.get('expect_used',0)}用/{pb.get('expect_hit',0)}中 · "
         f"gates {pb.get('gates',{}) or '—'} · loops {pb.get('loops',{}) or '—'} · "
         f"not_actionable {pb.get('not_actionable',0)} · 快照 {pb.get('snapshots',0)} · "
         f"errors {pb.get('errors',{}) or '—'}"]
    return "\n".join(L)


def _tasks_md(aggs):
    ids = sorted({tid for _, a in aggs for tid in a["per_task"]})
    head = "| 任务 | " + " | ".join(f"{lab} allpass / pass@1" for lab, _ in aggs) + " |"
    L = ["\n## 逐任务", head, "|---|" + "---|" * len(aggs)]
    for tid in ids:
        cells = []
        for _, a in aggs:
            t = a["per_task"].get(tid)
            cells.append(f"{t['all_pass_rate']:.0%} / {t['pass_at_1']:.0%}" if t else "—")
        L.append(f"| {tid} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap_files = [a for a in argv if not a.startswith("--")]
    if not ap_files:
        print("用法: report.py <base.jsonl> [new.jsonl] [--out report.md]")
        return 1
    ra = aggregate(load_results(ap_files[0]))
    rb = aggregate(load_results(ap_files[1])) if len(ap_files) > 1 else None
    la = Path(ap_files[0]).stem
    lb = Path(ap_files[1]).stem if len(ap_files) > 1 else ""
    md = render_markdown(ra, rb, la, lb)
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])
        out.write_text(md, encoding="utf-8")
        print(f"written -> {out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
