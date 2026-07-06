"""
检验模式 / GPU API 链路诊断。

Usage:
  python scripts/diagnose_inspect.py
  python scripts/diagnose_inspect.py --full    # 960×540 合成 UI 图 parse 探针
  python scripts/diagnose_inspect.py --llm     # OpenAI 最小探针（少量计费，判定可达性）
  python scripts/diagnose_inspect.py --e2e     # A 端 /inspect 端到端（无 OpenAI 计费）
  python scripts/diagnose_inspect.py --process # A 端 /process 端到端（L3 可能调用 LLM）
  python scripts/diagnose_inspect.py --fast    # 断言 fast 模式 e2e process 总耗时 <5s
  python scripts/diagnose_inspect.py --l2      # 断言 L2 模板跳过 parse
  python scripts/diagnose_inspect.py --real-screen  # 探针 vs 实屏 parse 对比
  python scripts/diagnose_inspect.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.chain_diagnostics import format_report_human, run_full_diagnostic  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="HAJIMI chain diagnostics (mode-aware)")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run OmniParser /parse/ probe with 960×540 synthetic UI PNG",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Probe OpenAI LLM API reachability (minimal chat, small billing)",
    )
    parser.add_argument(
        "--e2e",
        action="store_true",
        help="Run A-end POST /api/demo/inspect end-to-end",
    )
    parser.add_argument(
        "--process",
        action="store_true",
        help="Run A-end POST /api/demo/process end-to-end (L3, may call LLM)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Assert fast-mode e2e /process completes in under 5s without vision",
    )
    parser.add_argument(
        "--l2",
        action="store_true",
        help="Assert L2 template /process skips GPU parse (parse_skipped=true)",
    )
    parser.add_argument(
        "--real-screen",
        action="store_true",
        help="Compare GPU parse: synthetic probe vs real desktop capture",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable report",
    )
    args = parser.parse_args()

    report = run_full_diagnostic(
        include_parse=args.full or args.real_screen,
        include_e2e_inspect=args.e2e,
        include_e2e_process=args.process,
        include_llm=args.llm,
        include_fast_assert=args.fast,
        include_real_screen=args.real_screen,
        include_l2_assert=args.l2,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report_human(report))

    return 0 if report.overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
