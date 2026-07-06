"""
蓝图状态机补全测试（P3）

覆盖 server/services/planning/blueprint_engine.py 中新增的状态迁移：
- suspended -> advance（恢复执行）
- executing -> suspend（挂起）
- rolling_back -> advance（与 executing 行为一致）
- strict_fingerprint 真实指纹比对
"""
import pytest

from server.services.planning.blueprint_engine import BlueprintEngine
from server.storage.memory import TaskState
from server.models.schemas import Blueprint, Step, Intent


class TestBlueprintEngineP3:
    """P3 状态机补全测试"""

    def _make_state(
        self,
        total_steps: int = 3,
        current_step: int = 1,
        state: str = "executing",
        fingerprint: str | None = None,
    ) -> TaskState:
        steps = [
            Step(step_index=i + 1, action=f"步骤{i+1}", description="", status="pending")
            for i in range(total_steps)
        ]
        return TaskState(
            task_id="test-task",
            query="测试",
            intent=Intent(
                category="operation_guide",
                summary="测试",
                reference_type="explicit",
                confidence=0.9,
                needs_clarification=False,
            ),
            blueprint=Blueprint(
                name="测试", total_steps=total_steps, current_step=current_step, state=state
            ),
            steps=steps,
            ui_elements=[],
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
            fingerprint=fingerprint,
        )

    def test_advance_from_suspended_resumes_without_moving_pointer(self):
        """suspended 状态 advance 应恢复 executing，且不推进指针"""
        state = self._make_state(total_steps=3, current_step=2, state="suspended")
        state.steps[1].status = "active"

        action, next_step = BlueprintEngine.advance(state)

        assert action == "advance"
        assert state.blueprint.state == "executing"
        assert state.blueprint.current_step == 2
        assert state.steps[1].status == "active"
        assert next_step.step_index == 2

    def test_advance_from_executing_moves_pointer(self):
        """executing 状态 advance 应正常推进"""
        state = self._make_state(total_steps=3, current_step=1, state="executing")

        action, next_step = BlueprintEngine.advance(state)

        assert action == "advance"
        assert state.blueprint.state == "executing"
        assert state.blueprint.current_step == 2
        assert state.steps[0].status == "done"
        assert state.steps[1].status == "active"
        assert next_step.step_index == 2

    def test_suspend_from_executing_sets_suspended(self):
        """executing 状态 suspend 应变为 suspended"""
        state = self._make_state(total_steps=3, current_step=1, state="executing")

        action = BlueprintEngine.suspend(state)

        assert action == "suspended"
        assert state.blueprint.state == "suspended"

    def test_suspend_from_non_executing_does_nothing(self):
        """非 executing 状态调用 suspend 不应改变状态"""
        state = self._make_state(total_steps=3, current_step=1, state="completed")

        action = BlueprintEngine.suspend(state)

        assert action == "suspended"
        assert state.blueprint.state == "completed"

    def test_advance_from_rolling_back_behaves_like_executing(self):
        """rolling_back 状态 advance 应与 executing 行为一致"""
        state = self._make_state(total_steps=3, current_step=1, state="rolling_back")
        state.steps[0].status = "active"

        action, next_step = BlueprintEngine.advance(state)

        assert action == "advance"
        assert state.blueprint.state == "executing"
        assert state.blueprint.current_step == 2
        assert state.steps[0].status == "done"
        assert state.steps[1].status == "active"
        assert next_step.step_index == 2

    def test_strict_fingerprint_match_advances(self):
        """strict_fingerprint=True 且指纹匹配时正常推进"""
        state = self._make_state(
            total_steps=3,
            current_step=1,
            state="executing",
            fingerprint="same-fingerprint",
        )

        action, next_step = BlueprintEngine.advance(
            state, strict_fingerprint=True, fingerprint="same-fingerprint"
        )

        assert action == "advance"
        assert state.blueprint.state == "executing"
        assert state.blueprint.current_step == 2
        assert next_step.step_index == 2

    def test_strict_fingerprint_mismatch_suspends(self):
        """strict_fingerprint=True 且指纹不匹配时挂起"""
        state = self._make_state(
            total_steps=3,
            current_step=1,
            state="executing",
            fingerprint="expected-fingerprint",
        )
        state.steps[0].status = "active"

        action, next_step = BlueprintEngine.advance(
            state, strict_fingerprint=True, fingerprint="wrong-fingerprint"
        )

        assert action == "suspended"
        assert state.blueprint.state == "suspended"
        assert state.blueprint.current_step == 1
        assert state.steps[0].status == "active"
        assert next_step.step_index == 1

    def test_strict_fingerprint_with_no_stored_fingerprint_advances(self):
        """state.fingerprint 为空时，strict_fingerprint=True 也不应挂起"""
        state = self._make_state(
            total_steps=3, current_step=1, state="executing", fingerprint=None
        )

        action, next_step = BlueprintEngine.advance(
            state, strict_fingerprint=True, fingerprint="any-fingerprint"
        )

        assert action == "advance"
        assert state.blueprint.state == "executing"
        assert state.blueprint.current_step == 2

    def test_terminate_from_suspended(self):
        """suspended 状态 terminate 应变为 terminated"""
        state = self._make_state(total_steps=3, current_step=2, state="suspended")

        action = BlueprintEngine.terminate(state)

        assert action == "terminated"
        assert state.blueprint.state == "terminated"
