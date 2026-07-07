"""
HAJIMI Demo 蓝图状态机
实现 advance / rollback / skip / terminate 四种操作
"""
from typing import Tuple

from server.storage.memory import TaskState
from server.models.schemas import Blueprint, Step


class BlueprintEngine:
    """蓝图状态机引擎"""

    @staticmethod
    def advance(state: TaskState, strict_fingerprint: bool = False) -> Tuple[str, Step]:
        """
        推进到下一步
        返回: (action, next_step)
        """
        bp = state.blueprint
        steps = state.steps

        # 如果已经完成或终止，直接返回
        if bp.state in ("completed", "terminated"):
            return "complete", None

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

        # 进入执行状态
        bp.state = "executing"
        next_idx = bp.current_step - 1
        steps[next_idx].status = "active"

        # Demo 阶段：模拟 10% 概率挂起（测试用）
        # 生产阶段应比较 fingerprint
        if strict_fingerprint:
            # 这里可以添加真实的指纹比对逻辑
            pass

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
    def skip(state: TaskState) -> Tuple[str, Step]:
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
