"""L5 评测 runner（T3）——Windows 上执行：任务集 × seeds × repeats，oracle 判分。

用法（Windows，server_A venv）:
    python eval/run_eval.py --repeats 4 --label master-t1 [--only id1,id2]
                            [--base-url http://127.0.0.1:8011] [--dry-run]
每实例流程：PS setup → POST /execute → 消费 SSE 至终态/超时 cancel → oracle →
cleanup → 结果行写 eval_results/<label>.jsonl（含引擎遥测 runs.jsonl 关联字段）。
判分：oracle 为真 且 final_status 与 expect_status 一致。
UIA/注册表探测仅在真跑时 import（--dry-run 与单测在 Linux 可跑）。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval import load_tasks  # noqa: E402
from eval.oracle_eval import eval_oracle  # noqa: E402

HERE = Path(__file__).resolve().parent
TERMINAL_EVENTS = {"task_done", "task_failed", "task_cancelled"}


# ── 纯逻辑（跨平台可测） ────────────────────────────────────────────────


def expand_macros(obj, eval_dir: str):
    """把 {EVAL_DIR} 宏替换为真实目录（runner 启动前统一展开）。"""
    if isinstance(obj, str):
        return obj.replace("{EVAL_DIR}", eval_dir)
    if isinstance(obj, list):
        return [expand_macros(x, eval_dir) for x in obj]
    if isinstance(obj, dict):
        return {k: expand_macros(v, eval_dir) for k, v in obj.items()}
    return obj


def plan_instances(tasks, repeats: int, order_seed: int = 7):
    """展开 (task, seed, rep) 实例并乱序（固定 order_seed 可复现顺序）。"""
    insts = []
    for t in tasks:
        for seed in t.seeds:
            for rep in range(max(1, repeats)):
                insts.append({"task": t.render(seed), "seed": seed, "rep": rep,
                              "instance_id": f"{t.id}#{seed}#{rep}"})
    rng = random.Random(order_seed)
    rng.shuffle(insts)
    return insts


def judge(oracle_ok: bool, final_status: str, expect_status: str) -> bool:
    return bool(oracle_ok) and final_status == expect_status


def parse_sse_stream(resp, deadline: float):
    """从 /stream 响应读事件流至终态或超时。返回 (terminal_event_name|None, data)。"""
    event = None
    while time.time() < deadline:
        line = resp.readline()
        if not line:
            break
        s = line.decode("utf-8", errors="replace").strip()
        if s.startswith("event:"):
            event = s.split(":", 1)[1].strip()
        elif s.startswith("data:") and event in TERMINAL_EVENTS:
            try:
                data = json.loads(s.split(":", 1)[1].strip())
            except Exception:
                data = {}
            return event, data
    return None, {}


def last_run_telemetry(runs_path: Path, task_id: str):
    """从引擎 runs.jsonl 里取该 task 的遥测行（可能尚未落盘→None）。"""
    try:
        with open(runs_path, "r", encoding="utf-8") as f:
            found = None
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("task_id") == task_id:
                    found = r
            return found
    except Exception:
        return None


def summarize_tel(tele_row):
    """把引擎遥测行压成评测关心的摘要（跨版本缺字段容错）。"""
    if not tele_row:
        return None
    acc = {"llm_calls": 0, "tokens": 0, "rounds": 0, "loops": {}, "gates": {},
           "expect_used": 0, "expect_hit": 0, "errors": {}, "not_actionable": 0,
           "snapshots": 0, "snap_latency_ms": []}
    for st in tele_row.get("steps", []):
        tel = st.get("tel") or {}
        if not isinstance(tel, dict):
            continue
        acc["llm_calls"] += tel.get("llm_calls", 0) or 0
        acc["tokens"] += (tel.get("tokens_prompt", 0) or 0) + (tel.get("tokens_completion", 0) or 0)
        acc["rounds"] += tel.get("rounds", 0) or 0
        acc["not_actionable"] += tel.get("not_actionable", 0) or 0
        for k, v in (tel.get("loop_events") or {}).items():
            acc["loops"][k] = acc["loops"].get(k, 0) + (v or 0)
        for k, v in (tel.get("gates") or {}).items():
            acc["gates"][k] = acc["gates"].get(k, 0) + (v or 0)
        e = tel.get("expect") or {}
        acc["expect_used"] += e.get("used", 0)
        acc["expect_hit"] += e.get("hit", 0)
        for k, v in (tel.get("errors") or {}).items():
            acc["errors"][k] = acc["errors"].get(k, 0) + (v or 0)
        s = tel.get("snapshots") or {}
        acc["snapshots"] += s.get("count", 0)
        acc["snap_latency_ms"] += (s.get("latency_ms") or [])[:16]
    return acc


def classify_failure(final_status: str, oracle_ok: bool, tel_sum, cancelled: bool):
    """四类失败打标（对齐报告文献口径），pass 时返回 None。"""
    if oracle_ok and final_status == "success":
        return None
    if cancelled:
        return "environment/timeout"
    errors = (tel_sum or {}).get("errors", {})
    loops = (tel_sum or {}).get("loops", {})
    if sum(loops.values()) > 0:
        return "progress-perception(卡死)"
    if errors.get("element_not_found") or errors.get("name_mismatch"):
        return "grounding(选错/选不到控件)"
    if (tel_sum or {}).get("snapshots", 0) == 0 and final_status != "success":
        return "perceptual(未观察就失败)"
    if (tel_sum or {}).get("not_actionable", 0) > 0:
        return "perceptual(控件不可操作)"
    return "recovery(执行偏航)"


# ── Windows 真跑部分 ────────────────────────────────────────────────────


class WindowsProbe:
    def __init__(self):
        import glob as _g
        import os as _os

        self._glob, self._os = _g, _os

    def file_exists(self, path):
        return self._os.path.exists(path)

    def read_text(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return None

    def glob_count(self, pattern):
        try:
            return len(self._glob.glob(pattern))
        except Exception:
            return 0

    def reg_value(self, hive, key, name):
        try:
            import winreg

            h = getattr(winreg, hive)
            with winreg.OpenKey(h, key) as k:
                return winreg.QueryValueEx(k, name)[0]
        except Exception:
            return None

    def clipboard(self):
        try:
            import pyperclip

            return pyperclip.paste()
        except Exception:
            return ""

    def window_titles(self):
        try:
            import uiautomation as auto

            root = auto.GetRootControl()
            out = []
            for w in root.GetChildren():
                try:
                    n = (w.Name or "").strip()
                    if n:
                        out.append(n)
                except Exception:
                    pass
            return out
        except Exception:
            return []

    def element_names(self, window_title_contains=None, element_type=None):
        try:
            import uiautomation as auto

            roots = auto.GetRootControl().GetChildren()
            names = []
            for w in roots:
                try:
                    title = (w.Name or "").lower()
                except Exception:
                    title = ""
                if window_title_contains and window_title_contains not in title:
                    continue
                self._collect(w, 0, names)
            return names
        except Exception:
            return []

    def _collect(self, ctrl, depth, names, budget=None):
        budget = budget if budget is not None else [800]
        if depth > 8 or budget[0] <= 0:
            return
        budget[0] -= 1
        try:
            n = (ctrl.Name or "").strip()
            if n:
                names.append(n)
            for c in ctrl.GetChildren():
                self._collect(c, depth + 1, names, budget)
        except Exception:
            return


def run_ps(lines, env=None):
    for line in lines or []:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", line],
            capture_output=True, text=True, timeout=60, env=env,
        )


def http_post(url, payload, headers=None, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="L5 回归评测 runner")
    ap.add_argument("--tasks", default=str(HERE / "tasks"))
    ap.add_argument("--repeats", type=int, default=4)
    ap.add_argument("--label", default=time.strftime("%Y%m%d-%H%M"))
    ap.add_argument("--base-url", default=os.getenv("L5_API_URL", "http://127.0.0.1:8011"))
    ap.add_argument("--demo-key", default=os.getenv("HAJIMI_DEMO_KEY", "hajimi-demo-2026"))
    ap.add_argument("--only", default="", help="逗号分隔任务 id")
    ap.add_argument("--order-seed", type=int, default=7)
    ap.add_argument("--out", default=str(HERE / "results"))
    ap.add_argument("--dry-run", action="store_true", help="只列实例计划，不执行")
    args = ap.parse_args(argv)

    eval_dir = os.path.join(
        os.getenv("LOCALAPPDATA") or os.path.expanduser("~"), "HAJIMI", "eval"
    )
    tasks = load_tasks(Path(args.tasks))
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        tasks = [t for t in tasks if t.id in want]

    insts = plan_instances(tasks, args.repeats, args.order_seed)
    # {EVAL_DIR} 宏在实例级统一展开（instruction/setup/cleanup/oracle）
    for it in insts:
        t = it["task"]
        t.instruction = expand_macros(t.instruction, eval_dir)
        t.setup_ps1 = expand_macros(t.setup_ps1, eval_dir)
        t.cleanup_ps1 = expand_macros(t.cleanup_ps1, eval_dir)
        t.oracle = expand_macros(t.oracle, eval_dir)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_fp = out_dir / f"{args.label}.jsonl"
    done_ids = set()
    if out_fp.exists():
        for line in out_fp.read_text(encoding="utf-8").splitlines():
            try:
                done_ids.add(json.loads(line)["instance_id"])
            except Exception:
                pass

    if args.dry_run:
        for it in insts[:60]:
            print(it["instance_id"])
        print(f"[dry-run] instances={len(insts)} eval_dir={eval_dir} already_done={len(done_ids)}")
        return 0

    probe = WindowsProbe()
    runs_path = Path(eval_dir).parents[2] / "data" / "eval" / "runs.jsonl"
    # server_A/data/eval（与 eval_telemetry 默认一致）
    runs_path = HERE.parent / "data" / "eval" / "runs.jsonl"
    headers = {"X-Demo-Key": args.demo_key}
    ps_env = dict(os.environ, EVAL_DIR=eval_dir)

    executed = 0
    for it in insts:
        if it["instance_id"] in done_ids:
            continue
        t = it["task"]
        rec = {"instance_id": it["instance_id"], "task_id": t.id, "seed": it["seed"],
               "rep": it["rep"], "label": args.label, "expect_status": t.expect_status}
        t0 = time.time()
        cancelled = False
        try:
            run_ps(t.setup_ps1, ps_env)
            resp = http_post(f"{args.base_url}/api/demo/execute",
                             {"query": t.instruction, "image": None, "context": []},
                             headers=headers, timeout=60)
            backend_task_id = resp.get("task_id")
            rec["backend_task_id"] = backend_task_id
            deadline = t0 + t.max_wall_s
            with urllib.request.urlopen(
                f"{args.base_url}/api/demo/stream/{backend_task_id}", timeout=30
            ) as stream:
                ev, data = parse_sse_stream(stream, deadline)
            if ev is None:
                cancelled = True
                try:
                    http_post(f"{args.base_url}/api/demo/cancel", {"task_id": backend_task_id},
                              headers=headers, timeout=10)
                except Exception:
                    pass
                final = "timeout"
            else:
                final = "success" if ev == "task_done" else "fail"
            tele_row = last_run_telemetry(runs_path, backend_task_id)
            tel_sum = summarize_tel(tele_row)
            oracle_ok, trace = eval_oracle(t.oracle, probe)
            expected = t.expect_status  # success/fail
            got = "success" if final == "success" else "fail"
            rec.update({
                "final_status": got, "terminal_event": ev, "cancelled": cancelled,
                "oracle_ok": oracle_ok, "oracle_trace": trace,
                "pass": judge(oracle_ok, got, expected),
                "tel": tel_sum, "category_fail": classify_failure(
                    got, oracle_ok and got == expected, tel_sum, cancelled),
                "wall_s": round(time.time() - t0, 1),
            })
        except Exception as e:
            rec.update({"pass": False, "error": f"runner: {type(e).__name__}: {e}",
                        "wall_s": round(time.time() - t0, 1)})
        finally:
            try:
                run_ps(t.cleanup_ps1, ps_env)
            except Exception:
                pass
        executed += 1
        with open(out_fp, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        print(f"[{executed}] {it['instance_id']} pass={rec.get('pass')} "
              f"wall={rec.get('wall_s')}s")
    print(f"done -> {out_fp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
