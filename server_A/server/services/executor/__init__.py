"""
HAJIMI 自动操作助手 — 执行引擎
"""

from server.services.executor.clicker import (
    click_at,
    execute_action,
    press_keys,
    type_text,
)
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
    "execute_action",
    "click_at",
    "type_text",
    "press_keys",
    "check_step",
    "check_query",
    "SafetyResult",
]
