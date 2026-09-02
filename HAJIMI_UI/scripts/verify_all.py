# [VERIFY] 一键交接验收 — L5 自动执行模式
# 用途: 顺序运行 check_ui_env + verify_* 并输出汇总表
# 运行: python scripts/verify_all.py  或  scripts\verify_all.bat
"""HAJIMI 交接验收一键脚本（仅 L5 自动执行模式）。

默认跑 B 端项（无需 Sidecar）；verify_l5 在 :8011 不可达时 SKIP。
全栈: python scripts/verify_all.py --require-l5
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class StepResult:
    label: str
    status: Status
    detail: str = ""


def _pad_line(index: int, total: int, label: str, status: Status, width: int = 42) -> str:
    dots = max(1, width - len(label))
    return f"[{index}/{total}] {label} {'.' * dots} {status.value}"


def _run_subprocess(
    script: str,
    args: Optional[List[str]] = None,
    *,
    quiet: bool = False,
) -> tuple[int, str]:
    cmd = [sys.executable, str(SCRIPTS / script)]
    if args:
        cmd.extend(args)
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=quiet,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def _l5_sidecar_reachable() -> bool:
    sys.path.insert(0, str(ROOT))
    try:
        from core.api_client import check_l5_health

        return bool(check_l5_health())
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="HAJIMI 交接验收一键脚本 (L5)")
    parser.add_argument(
        "--require-l5",
        action="store_true",
        help="L5 Sidecar 不可达时整体失败（全栈/CI 模式）",
    )
    parser.add_argument("--skip-env", action="store_true", help="跳过 check_ui_env")
    parser.add_argument("-q", "--quiet", action="store_true", help="折叠子脚本输出")
    args = parser.parse_args()

    steps: list[tuple[str, Optional[str], Optional[list[str]], bool]] = []

    if not args.skip_env:
        steps.append(("check_ui_env", "check_ui_env.py", None, True))
    steps.extend(
        [
            ("verify_bc_signals", "verify_bc_signals.py", None, True),
            ("verify_settings_fragment", "verify_settings_fragment.py", None, True),
            ("verify_theme_apply", "verify_theme_apply.py", None, True),
        ]
    )
    l5_ok = _l5_sidecar_reachable()
    if l5_ok or args.require_l5:
        steps.append(("verify_l5", "verify_l5.py", ["--require-l5"], True))
    else:
        steps.append(("verify_l5", None, None, False))

    total = len(steps)
    results: List[StepResult] = []

    print("=== HAJIMI 交接验收 (verify_all, L5 auto-execute) ===")
    print(f"工作目录: {ROOT}\n")

    for idx, (name, script, script_args, should_run) in enumerate(steps, start=1):
        if not should_run:
            detail = "L5 Sidecar 不可达 :8011（先 启动全栈.bat 或 scripts\\start_l5_sidecar.bat）"
            if args.require_l5:
                results.append(StepResult(name, Status.FAIL, detail))
                print(_pad_line(idx, total, name, Status.FAIL) + f"  ({detail})")
            else:
                results.append(StepResult(name, Status.SKIP, detail))
                print(_pad_line(idx, total, name, Status.SKIP) + f"  ({detail})")
            continue

        display = name
        if script_args:
            display = f"{name} {' '.join(script_args)}"

        code, output = _run_subprocess(script, script_args, quiet=args.quiet)
        if code == 0:
            results.append(StepResult(name, Status.PASS))
            print(_pad_line(idx, total, display, Status.PASS))
        else:
            results.append(StepResult(name, Status.FAIL, f"exit {code}"))
            print(_pad_line(idx, total, display, Status.FAIL) + f"  (exit {code})")
            if output.strip():
                print("--- 子脚本输出 ---")
                print(output.rstrip())
                print("---")

    passed = sum(1 for r in results if r.status == Status.PASS)
    failed = sum(1 for r in results if r.status == Status.FAIL)
    skipped = sum(1 for r in results if r.status == Status.SKIP)

    print()
    print(f"汇总: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    if skipped and not args.require_l5:
        print("提示: 全栈验收请先 启动全栈.bat（8011 Sidecar + B 端）再运行 verify_all.bat --require-l5")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
