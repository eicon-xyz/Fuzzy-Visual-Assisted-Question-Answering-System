"""
L4 Vision 快路径 — 与 L2/L3/OmniParser 解耦的独立实现。

对外入口：
  - run_l4_process      首次 process（plan + 首步 locate）
  - run_l4_locate_step  单步 Vision 定位
"""
from server.services.l4.orchestrator import run_l4_locate_step, run_l4_process

__all__ = ["run_l4_process", "run_l4_locate_step"]
