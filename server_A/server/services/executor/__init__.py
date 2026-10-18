"""
HAJIMI 自动操作助手 — 执行引擎

注意：这里**不再**再导出 `click_at` / `type_text` / `press_keys` / `execute_action`。
包级再导出等于给 HID 开了一个不受许可约束的后门（Phase 1 已收口）。
需要键鼠注入请走 `server.services.executor.hid`，它要求显式的接管许可。
"""

from server.services.executor.engine import (
    cancel_task,
    register_task,
    run_plan,
    unregister_task,
)
from server.services.executor.safety import SafetyResult, check_query, check_step

__all__ = [
    "run_plan",
    "cancel_task",
    "register_task",
    "unregister_task",
    "check_step",
    "check_query",
    "SafetyResult",
]
