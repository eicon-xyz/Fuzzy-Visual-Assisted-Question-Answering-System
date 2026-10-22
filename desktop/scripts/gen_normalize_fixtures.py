# -*- coding: utf-8 -*-
"""生成 desktop/core/redline/normalize.ts 的 parity golden 语料。

用现行 Python 实现（HAJIMI_UI/core/l5_query_normalize + server_A redline_service）
对语料逐条归一化，同时以 spy 记录每一次红线判定的输入→结果。
vitest 侧用该 trace 构造 checker 并断言最终输出逐条相等——
若 TS 改写的中间形态与 Python 不一致，trace 缺失会使输出偏离而被捕获。

用法（repo 根）：python3 desktop/scripts/gen_normalize_fixtures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "HAJIMI_UI"))

from core import sidecar_modules  # noqa: E402
from core import l5_query_normalize as lqn  # noqa: E402

_real_check = sidecar_modules.get_redline_check()
if _real_check is None:
    raise SystemExit("server_A redline_service 不可达，无法生成语料")

TRACE: dict[str, dict] = {}


def _spy_check(query: str):
    r = _real_check(query)
    TRACE[query] = {"triggered": bool(r.triggered), "category": r.category or ""}
    return r


lqn._check = _spy_check  # 注入 spy（仅本进程）

# 语料：Python 测试用例全集 + 五段改写路径/降级语义的扩展覆盖
CORPUS = [
    # 现有 test_l5_query_normalize.py
    "帮我自动点击下载按钮",
    "用脚本自动刷票",
    "帮我抢票",
    "每5秒自动点击一次确认按钮",
    "有没有破解软件的外挂",
    "帮我打开微信",
    "帮我打开记事本",
    "帮我扫描硬盘里所有的照片",  # personal_privacy → 原样
    "",
    "   ",
    "怎么安装微信？",
    "打开记事本",
    # 扩展：前缀剥离 / 各替换档
    "请帮我自动操作浏览器",
    "替我执行脚本",
    "代我 下载 文件",
    "全自动批量发送消息",
    "每分钟自动循环签到",
    "给我破解这个外挂",  # physical+工具替换组合
    "一直自动点击刷新",
    "定时重复打开设置",
    # realtime_dynamic 类应原样（若规则命中）
    "现在天气怎么样",
    # 无红线词 → 原样直通
    "打开计算器然后输入 123",
    "搜索 HAJIMI 的官网",
    # 边界：只有前缀
    "帮我",
    "请帮我",
    # 深层改写路径探针（多轮 strip 后仍触发的构造）
    "帮我自动打开自动售卖机并自动付款",
    "循环自动点击领取",
]


def main() -> None:
    cases = []
    for q in CORPUS:
        TRACE.clear()
        out = lqn.normalize_l5_execute_query(q)
        cases.append(
            {
                "input": q,
                "output": out,
                "trace": dict(TRACE),
            }
        )
    dest = ROOT / "desktop" / "tests" / "fixtures" / "normalize_golden.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedBy": "desktop/scripts/gen_normalize_fixtures.py",
        "note": "trace 记录 normalize 全过程中每次红线判定 query→verdict",
        "cases": cases,
    }
    dest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"written {dest} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
