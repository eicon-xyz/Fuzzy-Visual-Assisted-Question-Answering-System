"""L4 步骤类型判定：keyboard / deferred / 需 Vision 定位。"""
from __future__ import annotations

_KEYBOARD_ACTIONS = frozenset(
    {"type", "hotkey", "keyboard", "input", "wait", "open_app"}
)
_DEFER_KEYWORDS = (
    "等待",
    "稍候",
    "加载中",
    "完成后",
    "切换窗口",
    "切换到",
    "切换至",
    "打开应用",
    "先手动",
)


def is_non_interactive_step(description: str, action: str) -> bool:
    text = f"{description} {action}"
    return any(k in text for k in _DEFER_KEYWORDS)


def apply_step_interaction(step: dict) -> dict:
    """补全 interaction / locate_deferred / prepare_hint。"""
    action = (step.get("action") or "").lower()
    desc = step.get("description") or step.get("target") or ""

    if not step.get("interaction"):
        if action in _KEYBOARD_ACTIONS:
            step["interaction"] = "keyboard"
        else:
            step["interaction"] = "screen"

    if step.get("interaction") == "keyboard":
        return step

    if is_non_interactive_step(desc, action):
        step["locate_deferred"] = True
        step.setdefault("prepare_hint", desc or action)

    return step


def step_needs_locate(step: dict) -> bool:
    step = apply_step_interaction(dict(step))
    if step.get("locate_deferred"):
        return False
    if step.get("interaction") == "keyboard":
        return False
    action = (step.get("action") or "").lower()
    if action in _KEYBOARD_ACTIONS:
        return False
    return True
