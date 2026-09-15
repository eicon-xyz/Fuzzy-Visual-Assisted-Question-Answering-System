"""L5 评测遥测（计划 T1）：任务级结构化记录落盘 + Transaction.result 回写。

设计约束（红线）：
  * 绝不影响执行链：所有落盘/回写包 try/except，失败只 debug 日志；
  * 不新增依赖：stdlib；git sha 一次性 subprocess，失败回退 "unknown"；
  * 落盘位置：server_A/data/eval/runs.jsonl（每行一个任务 JSON，供
    eval runner / report 消费）；测试可用环境变量 HAJIMI_EVAL_DIR 重定向。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DIR = _REPO_ROOT / "server_A" / "data" / "eval"

_lock = threading.Lock()
_git_sha_cache: Optional[str] = None


def git_sha() -> str:
    """当前运行代码的 git 短 sha（评测批次标签用），失败返回 unknown。"""
    global _git_sha_cache
    if _git_sha_cache is None:
        try:
            import subprocess

            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=5,
            )
            _git_sha_cache = out.stdout.strip() or "unknown"
        except Exception:
            _git_sha_cache = "unknown"
    return _git_sha_cache


def runs_file() -> Path:
    base = os.getenv("HAJIMI_EVAL_DIR")
    return (Path(base) if base else _DEFAULT_DIR) / "runs.jsonl"


def new_step_telemetry() -> dict:
    """单步遥测模板（agent.execute_step 每步新建，就地累加）。"""
    return {
        "rounds": 0,
        "llm_calls": 0,
        "tokens_prompt": 0,
        "tokens_completion": 0,
        "tool_calls": {},
        "errors": {},
        "slowest_ms": {},
        "expect": {"used": 0, "hit": 0},
        "gates": {
            "done_refused": 0,
            "failed_refused": 0,
            "unverified_done": 0,
        },
        "loop_events": {
            "repeat5": 0,
            "repeat8": 0,
            "repeat12": 0,
            "stagnation": 0,
            "replan": 0,
        },
        "not_actionable": 0,
        "snapshots": {"count": 0, "latency_ms": [], "nodes": 0},
    }


def tally_tool(tel: Optional[dict], tool: str, result: dict, duration_ms: int = 0) -> None:
    """把一次工具调用记入步遥测（纯函数，None 安全）。"""
    if tel is None or not isinstance(result, dict):
        return
    tel["rounds"] = tel.get("rounds", 0) + 1
    tc = tel["tool_calls"]
    tc[tool] = tc.get(tool, 0) + 1
    # 0ms 是合法值（mock/快路径），不用真值判断
    sm = tel["slowest_ms"]
    sm[tool] = max(sm.get(tool, 0), int(duration_ms))

    if result.get("expect_ok") is not None or "expect_detail" in result:
        if "expect_ok" in result:
            tel["expect"]["used"] += 1
            if result.get("expect_ok") is True:
                tel["expect"]["hit"] += 1
    gates = tel["gates"]
    code = result.get("error_code")
    if code == "done_without_evidence":
        gates["done_refused"] += 1
    elif code == "giveup_refused_retry":
        gates["failed_refused"] += 1
    if result.get("unverified_done"):
        gates["unverified_done"] = 1
    if code:
        if code == "not_actionable":
            tel["not_actionable"] += 1
        err = tel["errors"]
        err[code] = err.get(code, 0) + 1


def tally_llm_usage(tel: Optional[dict], usage: dict) -> None:
    if tel is None:
        return
    tel["llm_calls"] = tel.get("llm_calls", 0) + 1
    try:
        tel["tokens_prompt"] += int(usage.get("prompt_tokens") or 0)
        tel["tokens_completion"] += int(usage.get("completion_tokens") or 0)
    except Exception:
        pass


def tally_snapshot(tel: Optional[dict], latency_ms: int, nodes: int) -> None:
    if tel is None:
        return
    s = tel["snapshots"]
    s["count"] += 1
    if len(s["latency_ms"]) < 64:
        s["latency_ms"].append(int(latency_ms))
    s["nodes"] = max(s["nodes"], int(nodes))


def record_task(
    task_id: str,
    goal: str,
    steps: list,
    final_status: str,
    wall_ms: int,
    instruction: str = "",
) -> Optional[Path]:
    """任务终态落盘（engine 调用）。steps=[{idx,status,terminal_kind,evidence,tel}]。

    同时回写 Transaction.result（修复 L4 删除后断裂的 DB 统计链路）。
    """
    line = {
        "task_id": task_id,
        "ts": round(time.time(), 3),
        "git_sha": git_sha(),
        "goal": goal,
        "instruction": instruction,
        "final_status": final_status,
        "wall_ms": int(wall_ms),
        "steps": steps,
    }
    try:
        path = runs_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(line, ensure_ascii=False, default=str)
        with _lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(payload + "\n")
    except Exception:
        logger.debug("eval telemetry write failed", exc_info=True)
    try:
        from server.database.repository import TaskRepository

        TaskRepository.update_result(
            task_id,
            "success" if final_status == "success" else "fail",
            duration_ms=int(wall_ms),
        )
    except Exception:
        logger.debug("eval telemetry DB update_result failed", exc_info=True)
    return runs_file()
