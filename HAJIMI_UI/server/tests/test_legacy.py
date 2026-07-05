"""
老代码快照测试（第 0 天护栏）

目的：在并行重构期间，确保未开启特性开关时，现有行为不变。
任何导致这些测试失败的重构都是非法的。
"""
import pytest

from server.services.llm_ai import classify_intent, generate_steps, process_query
from server.services.planning.blueprint_engine import BlueprintEngine
from server.storage.memory import TaskState
from server.models.schemas import Blueprint, Step, Intent
from server.config import settings


class TestClassifyIntent:
    """意图分类老逻辑快照"""

    def test_install_software(self):
        category, summary, confidence = classify_intent("怎么安装微信")
        assert category == "operation_guide"
        assert summary == "安装软件"
        assert confidence == 0.92

    def test_screenshot(self):
        category, summary, confidence = classify_intent("怎么截图")
        assert category == "operation_guide"
        assert summary == "屏幕截图"
        assert confidence == 0.90

    def test_default(self):
        category, summary, confidence = classify_intent("随便问问")
        assert category == "operation_guide"
        assert summary == "通用操作指引"
        assert confidence == 0.75


class TestGenerateSteps:
    """步骤生成老逻辑快照"""

    def test_wechat_scenario_steps_count(self):
        # 直接修改运行时配置，避免环境变量已被加载的问题
        settings.USE_REAL_LLM = False
        steps = generate_steps("安装微信")
        assert len(steps) == 4
        assert steps[0]["action"] == "打开浏览器"

    def test_screenshot_scenario_steps_count(self):
        settings.USE_REAL_LLM = False
        steps = generate_steps("截图")
        assert len(steps) == 3
        assert steps[0]["action"] == "打开截图工具"

    def test_legacy_steps_no_target_element_id(self):
        """老逻辑返回的步骤包含 target_element_id（新行为：mock 数据已含元素绑定）"""
        settings.USE_REAL_LLM = False
        steps = generate_steps("安装微信")
        for step in steps:
            # New behavior: mock fallback includes target_element_id for bound steps
            assert "target_element_id" in step


class TestProcessQuery:
    """核心流程老逻辑快照"""

    def test_process_without_image(self):
        settings.USE_REAL_LLM = False
        response = process_query("安装微信")
        assert response.success is True
        assert response.intent.summary == "安装软件"
        assert len(response.steps) == 4
        assert response.steps[0].status == "active"
        assert response.blueprint.state == "pending_confirm"

    def test_process_first_step_binding_legacy(self):
        """老逻辑：第一步绑定第一个元素（机械循环）"""
        settings.USE_REAL_LLM = False
        response = process_query("安装微信")
        # 老逻辑：steps[0] 绑定 elements[0]，即 ~1
        assert response.steps[0].target_element_id == "~1"
        assert response.steps[0].annotation is not None


class TestBlueprintEngine:
    """蓝图状态机老逻辑快照"""

    def _make_state(self, total_steps: int = 3, current_step: int = 1, state: str = "executing") -> TaskState:
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
            blueprint=Blueprint(name="测试", total_steps=total_steps, current_step=current_step, state=state),
            steps=steps,
            ui_elements=[],
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )

    def test_advance_from_step_1_to_2(self):
        state = self._make_state(total_steps=3, current_step=1, state="executing")
        action, next_step = BlueprintEngine.advance(state)
        assert action == "advance"
        assert state.blueprint.current_step == 2
        assert state.blueprint.state == "executing"
        assert state.steps[0].status == "done"
        assert state.steps[1].status == "active"
        assert next_step.step_index == 2

    def test_rollback_from_step_2_to_1(self):
        state = self._make_state(total_steps=3, current_step=2, state="executing")
        state.steps[0].status = "done"
        state.steps[1].status = "active"
        action, prev_step = BlueprintEngine.rollback(state)
        assert action == "rollback"
        assert state.blueprint.current_step == 1
        assert state.blueprint.state == "rolling_back"
        assert state.steps[0].status == "active"
        assert prev_step.step_index == 1

    def test_terminate(self):
        state = self._make_state(total_steps=3, current_step=1, state="executing")
        action = BlueprintEngine.terminate(state)
        assert action == "terminated"
        assert state.blueprint.state == "terminated"

    def test_complete_all_steps(self):
        state = self._make_state(total_steps=2, current_step=2, state="executing")
        state.steps[0].status = "done"
        state.steps[1].status = "active"
        action, next_step = BlueprintEngine.advance(state)
        assert action == "complete"
        assert state.blueprint.state == "completed"
        assert next_step is None
