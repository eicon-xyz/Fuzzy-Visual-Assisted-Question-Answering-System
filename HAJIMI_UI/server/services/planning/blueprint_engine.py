"""
HAJIMI Demo 蓝图状态机
实现 advance / rollback / skip / terminate / suspend 五种操作
"""

from typing import Any, Dict, Optional, Tuple

from server.models.schemas import Step
from server.storage.memory import TaskState


def _build_constraint_hint(
    constraints: Optional[Dict[str, Any]], step_description: str
) -> str:
    """根据约束条件生成步骤描述后缀提示"""
    if not constraints:
        return ""

    hints = []
    desc = step_description.lower()

    if "install_path" in constraints and (
        "安装" in desc or "路径" in desc or "位置" in desc
    ):
        hints.append(f"（注意：{constraints['install_path']}）")
    if "save_path" in constraints and (
        "保存" in desc or "路径" in desc or "位置" in desc
    ):
        hints.append(f"（注意：{constraints['save_path']}）")
    if "version" in constraints and ("版本" in desc or "下载" in desc):
        hints.append(f"（注意：{constraints['version']}）")
    if "avoid_options" in constraints and (
        "勾选" in desc or "选项" in desc or "取消" in desc
    ):
        hints.append(f"（注意：{constraints['avoid_options']}）")

    return "".join(hints)


class BlueprintEngine:
    """蓝图状态机引擎"""

    @staticmethod
    def advance(
        state: TaskState,
        strict_fingerprint: bool = False,
        fingerprint: Optional[str] = None,
    ) -> Tuple[str, Optional[Step]]:
        """
        推进到下一步
        返回: (action, next_step)
        """
        bp = state.blueprint
        steps = state.steps

        # 如果已经完成或终止，直接返回
        if bp.state in ("completed", "terminated"):
            return "complete", None

        # 从挂起状态恢复：不推进指针，仅恢复执行
        if bp.state == "suspended":
            bp.state = "executing"
            current_idx = bp.current_step - 1
            if 0 <= current_idx < len(steps):
                steps[current_idx].status = "active"
                return "advance", steps[current_idx]
            return "advance", None

        # 真实指纹比对：不匹配则挂起当前步骤
        if strict_fingerprint:
            if (
                fingerprint is not None
                and state.fingerprint is not None
                and fingerprint != state.fingerprint
            ):
                bp.state = "suspended"
                current_idx = bp.current_step - 1
                if 0 <= current_idx < len(steps):
                    steps[current_idx].status = "active"
                return "suspended", (
                    steps[current_idx] if 0 <= current_idx < len(steps) else None
                )

        # 标记当前步骤为 done
        current_idx = bp.current_step - 1
        if 0 <= current_idx < len(steps):
            steps[current_idx].status = "done"

        # 推进指针
        bp.current_step += 1

        # 检查是否完成
        if bp.current_step > len(steps):
            bp.state = "completed"
            bp.current_step = len(steps)
            BlueprintEngine._mark_done(steps)
            return "complete", None

        # 进入执行状态（rolling_back 到此分支后与 executing 行为一致）
        bp.state = "executing"
        next_idx = bp.current_step - 1
        steps[next_idx].status = "active"

        # 追加约束提示（避免重复追加）
        hint = _build_constraint_hint(state.constraints, steps[next_idx].description)
        if hint and hint not in steps[next_idx].description:
            steps[next_idx].description += hint

        return "advance", steps[next_idx]

    @staticmethod
    def rollback(state: TaskState) -> Tuple[str, Step]:
        """回退一步"""
        bp = state.blueprint
        steps = state.steps

        if bp.current_step <= 1:
            # 已经在第一步，无法回退
            bp.state = "executing"
            return "rollback", steps[0]

        # 当前步骤重置为 pending
        current_idx = bp.current_step - 1
        if 0 <= current_idx < len(steps):
            steps[current_idx].status = "pending"

        # 回退指针
        bp.current_step -= 1
        bp.state = "rolling_back"

        prev_idx = bp.current_step - 1
        steps[prev_idx].status = "active"

        return "rollback", steps[prev_idx]

    @staticmethod
    def suspend(state: TaskState) -> str:
        """挂起当前蓝图（仅 executing 可挂起）"""
        bp = state.blueprint
        if bp.state == "executing":
            bp.state = "suspended"
        return "suspended"

    @staticmethod
    def skip(state: TaskState) -> Tuple[str, Optional[Step]]:
        """跳过当前步骤"""
        bp = state.blueprint
        steps = state.steps

        if bp.state in ("completed", "terminated"):
            return "complete", None

        current_idx = bp.current_step - 1
        if 0 <= current_idx < len(steps):
            steps[current_idx].status = "skipped"

        bp.current_step += 1

        if bp.current_step > len(steps):
            bp.state = "completed"
            bp.current_step = len(steps)
            return "complete", None

        bp.state = "executing"
        next_idx = bp.current_step - 1
        steps[next_idx].status = "active"
        return "advance", steps[next_idx]

    @staticmethod
    def terminate(state: TaskState) -> str:
        """终止蓝图"""
        bp = state.blueprint
        bp.state = "terminated"
        return "terminated"

    @staticmethod
    def confirm(state: TaskState) -> None:
        """用户确认开始执行蓝图"""
        if state.blueprint.state == "pending_confirm":
            state.blueprint.state = "executing"
            if state.steps:
                state.steps[0].status = "active"

    @staticmethod
    def _mark_done(steps: list[Step]) -> None:
        """将所有步骤标记为完成"""
        for step in steps:
            if step.status not in ("skipped", "failed"):
                step.status = "done"
