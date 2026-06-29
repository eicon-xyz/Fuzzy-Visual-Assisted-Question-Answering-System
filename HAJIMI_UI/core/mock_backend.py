import uuid
from typing import Any, Dict, List, Optional

# Demo 阶段内存任务表，供 advance_step Mock 使用
_TASK_STORE: Dict[str, Dict[str, Any]] = {}


def _bbox(x_ratio: float, y_ratio: float, w_ratio: float, h_ratio: float, sw: int, sh: int):
    x1 = int(sw * x_ratio)
    y1 = int(sh * y_ratio)
    x2 = int(sw * (x_ratio + w_ratio))
    y2 = int(sh * (y_ratio + h_ratio))
    return [x1, y1, x2, y2]


def _build_wechat_steps(sw: int, sh: int) -> List[Dict[str, Any]]:
    return [
        {
            "step_index": 1,
            "action": "打开浏览器",
            "description": "找到桌面上的 Microsoft Edge 图标，双击打开浏览器。",
            "target_element_id": "~1",
            "status": "active",
            "annotation": {
                "type": "arrow_highlight",
                "arrow_from": [int(sw * 0.05), int(sh * 0.35)],
                "arrow_to": [int(sw * 0.18), int(sh * 0.35)],
                "highlight_bbox": _bbox(0.12, 0.30, 0.10, 0.06, sw, sh),
                "label_text": "~1",
            },
        },
        {
            "step_index": 2,
            "action": "访问微信官网",
            "description": "在浏览器地址栏输入 weixin.qq.com 并回车。",
            "target_element_id": "~2",
            "status": "pending",
            "annotation": {
                "type": "highlight_only",
                "highlight_bbox": _bbox(0.35, 0.04, 0.30, 0.05, sw, sh),
            },
        },
        {
            "step_index": 3,
            "action": "点击下载按钮",
            "description": "在官网首页找到「下载」按钮并点击。",
            "target_element_id": "~3",
            "status": "pending",
            "annotation": {
                "type": "arrow_highlight",
                "arrow_from": [int(sw * 0.05), int(sh * 0.55)],
                "arrow_to": [int(sw * 0.75), int(sh * 0.55)],
                "highlight_bbox": _bbox(0.70, 0.50, 0.12, 0.06, sw, sh),
                "label_text": "~3",
            },
        },
    ]


def process_query(query: str, screen_width: int = 1920, screen_height: int = 1080) -> Optional[dict]:
    """Demo Mock：匹配「安装微信」类问题，返回 3 步 + 屏幕标注坐标。"""
    if "微信" not in query and "安装" not in query:
        return None

    sw, sh = screen_width, screen_height
    task_id = str(uuid.uuid4())
    steps = _build_wechat_steps(sw, sh)

    response = {
        "task_id": task_id,
        "success": True,
        "intent": {
            "category": "operation_guide",
            "summary": "安装微信",
            "reference_type": "explicit",
            "confidence": 0.92,
            "needs_clarification": False,
        },
        "ui_elements": [],
        "annotated_image": "",
        "blueprint": {
            "name": "安装微信",
            "total_steps": 3,
            "current_step": 1,
            "state": "executing",
        },
        "steps": steps,
        "_mock": True,
    }

    _TASK_STORE[task_id] = {
        "steps": steps,
        "current_step": 1,
        "screen_width": sw,
        "screen_height": sh,
    }
    return response


def register_task(task_id: str, steps: List[Dict[str, Any]]):
    """真实 API process 返回后注册任务，供 step Mock 回退使用。"""
    if task_id and steps:
        _TASK_STORE[task_id] = {"steps": steps, "current_step": 1}


def advance_step(
    task_id: str,
    step_index: int,
    fingerprint: str = "",
    action: str = "advance",
    steps: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    """
    Mock POST /api/demo/step
    默认 advance 成功；action=skip/rollback/terminate 按契约模拟。
    """
    task = _TASK_STORE.get(task_id)
    if not task and steps:
        _TASK_STORE[task_id] = {"steps": steps, "current_step": step_index}
        task = _TASK_STORE[task_id]
    if not task:
        task = {"steps": steps or [], "current_step": max(1, step_index)}

    all_steps = task.get("steps") or steps or []
    total = len(all_steps)

    if action == "terminate":
        task["current_step"] = step_index
        return {
            "task_id": task_id,
            "action": "terminated",
            "current_step": step_index,
            "blueprint_state": "terminated",
            "message": "任务已终止",
            "_mock": True,
        }

    if action == "rollback":
        new_step = max(1, step_index - 1)
        task["current_step"] = new_step
        idx = new_step - 1
        return {
            "task_id": task_id,
            "action": "rollback",
            "current_step": new_step,
            "blueprint_state": "rolling_back",
            "next_step": all_steps[idx] if 0 <= idx < total else None,
            "_mock": True,
        }

    if action == "skip":
        new_step = min(total, step_index + 1)
        task["current_step"] = new_step
        if new_step > total:
            return {
                "task_id": task_id,
                "action": "complete",
                "current_step": total,
                "blueprint_state": "completed",
                "_mock": True,
            }
        idx = new_step - 1
        return {
            "task_id": task_id,
            "action": "advance",
            "current_step": new_step,
            "blueprint_state": "executing",
            "next_step": all_steps[idx] if 0 <= idx < total else None,
            "_mock": True,
        }

    # advance：Mock 默认校验通过
    if step_index >= total:
        return {
            "task_id": task_id,
            "action": "complete",
            "current_step": total,
            "blueprint_state": "completed",
            "_mock": True,
        }

    new_step = step_index + 1
    task["current_step"] = new_step

    if new_step > total:
        return {
            "task_id": task_id,
            "action": "complete",
            "current_step": total,
            "blueprint_state": "completed",
            "_mock": True,
        }

    idx = new_step - 1
    return {
        "task_id": task_id,
        "action": "advance",
        "current_step": new_step,
        "blueprint_state": "executing",
        "next_step": all_steps[idx] if 0 <= idx < total else None,
        "_mock": True,
    }
