"""
P4「约束条件提取」单元测试

覆盖：
1. SYSTEM_PROMPT 输出含 constraints 字段
2. process_query 将 constraints 透传至 ProcessResponse
3. generate_steps 返回 steps + constraints 二元组
4. 蓝图执行时约束提示追加到步骤描述
"""
import pytest

from server.config import settings
from server.models.schemas import ProcessResponse, Step, Blueprint, Intent, UIElement
from server.services.planning.router import generate_steps, process_query
from server.services.planning.blueprint_engine import BlueprintEngine
from server.storage.memory import TaskState, task_store


@pytest.fixture(autouse=True)
def _disable_real_llm(monkeypatch):
    """关闭真实 LLM，确保使用 mock fallback"""
    monkeypatch.setattr(settings, "USE_REAL_LLM", False)


class TestConstraintSchema:
    """约束字段在数据模型中的存在性"""

    def test_process_response_has_constraints_field(self):
        response = ProcessResponse(
            task_id="test-1",
            success=True,
            intent=Intent(
                category="operation_guide",
                summary="安装微信",
                reference_type="explicit",
                confidence=0.92,
                needs_clarification=False,
            ),
            ui_elements=[],
            blueprint=Blueprint(
                name="安装微信",
                total_steps=2,
                current_step=1,
                state="pending_confirm",
            ),
            steps=[
                Step(
                    step_index=1,
                    action="打开浏览器",
                    description="双击浏览器图标",
                    target_element_id=None,
                    status="active",
                )
            ],
            constraints={"install_path": "非C盘"},
        )
        assert response.constraints == {"install_path": "非C盘"}


class TestGenerateStepsReturnValue:
    """generate_steps 返回 steps + constraints 二元组"""

    def test_mock_fallback_returns_none_constraints(self):
        steps, constraints = generate_steps("截图")
        assert len(steps) == 3
        assert constraints is None


class TestProcessQueryConstraints:
    """process_query 透传 constraints"""

    def test_process_query_without_constraints(self):
        response = process_query("截图")
        assert response.constraints is None


class TestBlueprintConstraintHint:
    """蓝图执行时追加约束提示"""

    def test_advance_appends_install_path_hint(self):
        state = TaskState(
            task_id="constraint-task",
            query="安装微信，不要装在C盘",
            intent=Intent(
                category="operation_guide",
                summary="安装微信",
                reference_type="explicit",
                confidence=0.92,
                needs_clarification=False,
            ),
            blueprint=Blueprint(
                name="安装微信",
                total_steps=3,
                current_step=1,
                state="executing",
            ),
            steps=[
                Step(
                    step_index=1,
                    action="打开浏览器",
                    description="双击桌面上的浏览器图标",
                    target_element_id="~1",
                    status="active",
                ),
                Step(
                    step_index=2,
                    action="运行安装程序",
                    description="下载完成后运行安装包",
                    target_element_id=None,
                    status="pending",
                ),
                Step(
                    step_index=3,
                    action="选择安装路径",
                    description="在安装向导中选择安装路径",
                    target_element_id=None,
                    status="pending",
                ),
            ],
            ui_elements=[],
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
            constraints={"install_path": "不要安装在 C 盘"},
        )

        # 推进到 Step 2，描述不含安装路径关键词，不应追加提示
        action, next_step = BlueprintEngine.advance(state)
        assert action == "advance"
        assert "不要安装在 C 盘" not in next_step.description

        # 推进到 Step 3，描述含安装路径关键词，应追加提示
        action, next_step = BlueprintEngine.advance(state)
        assert action == "advance"
        assert "不要安装在 C 盘" in next_step.description

        # 再次推进不应重复追加
        desc_before = state.steps[2].description
        BlueprintEngine.rollback(state)
        BlueprintEngine.advance(state)
        assert state.steps[2].description == desc_before
