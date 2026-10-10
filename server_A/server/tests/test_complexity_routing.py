"""
C06 — L2 快路径接线：复杂度路由、旁路与持久化

缝 S1：server.services.planning.router.process_query（公开入口）
覆盖：L2 模板命中 / 无模板降级 / L3 直通 / L2 跳过 OmniParser
"""

import pytest

from server.config import settings


@pytest.fixture(autouse=True)
def _l5_mode(monkeypatch):
    """固定 L5 口径（无 OmniParser），与部署和测试环境一致。"""
    monkeypatch.setattr(settings, "OMNIPARSER_ENABLED", False)


class TestL2FastPath:
    def test_template_hit_routes_l2_without_llm(self, monkeypatch):
        """『打开计算器』复杂度 9 → L2 模板步骤，不调用 LLM 规划。"""
        planner_calls = []

        def _spy_plan_steps(query, max_retries=2):
            planner_calls.append(query)
            raise AssertionError("L2 快路径不应调用 plan_steps")

        monkeypatch.setattr(
            "server.services.planning.planner.plan_steps", _spy_plan_steps
        )

        from server.services.planning.router import process_query

        response = process_query("打开计算器")

        assert response.success is True
        assert planner_calls == []
        assert response.detection_meta == {
            "backend": "template",
            "route": "L2",
            "complexity": 9,
        }  # 手算：int(5×0.3 + 1×8) = 9
        assert [s.instruction for s in response.steps] == [
            "在桌面或开始菜单找到 计算器 的图标",
            "双击 计算器 图标启动应用",
        ]
        assert all(s.status == "pending" for s in response.steps)


class TestL2Degrade:
    def test_unmatched_low_complexity_degrades_to_l3(self, monkeypatch):
        """『安装微信』复杂度 29（<30）但无模板命中 → 降级 L3，route 记实际路径。"""
        from server.models.schemas import PlanningStep
        from server.services.planning.planner import PlanningResult

        planner_calls = []

        def _fake_plan_steps(query, max_retries=2):
            planner_calls.append(query)
            return PlanningResult(
                goal="安装微信",
                steps=[PlanningStep(step_index=1, instruction="打开浏览器搜索微信官网")],
            )

        monkeypatch.setattr(
            "server.services.planning.planner.plan_steps", _fake_plan_steps
        )

        from server.services.planning.router import process_query

        response = process_query("安装微信")

        assert planner_calls == ["安装微信"]
        assert response.detection_meta == {
            "backend": "uia_execution",
            "route": "L3",
            "complexity": 29,
            "omniparser": "not_required",
        }  # 手算：int(4×0.3 + 1×8 + 2×10) = 29（降级后走 L3 实际路径）
        assert [s.instruction for s in response.steps] == ["打开浏览器搜索微信官网"]


class TestL3Direct:
    def test_high_complexity_goes_l3(self, monkeypatch):
        """『打开浏览器下载微信安装程序』复杂度 67（≥30）→ L3 直通。"""
        from server.models.schemas import PlanningStep
        from server.services.planning.planner import PlanningResult

        planner_calls = []

        def _fake_plan_steps(query, max_retries=2):
            planner_calls.append(query)
            return PlanningResult(
                goal="打开浏览器下载并安装微信",
                steps=[
                    PlanningStep(step_index=1, instruction="打开浏览器"),
                    PlanningStep(step_index=2, instruction="下载微信安装程序"),
                ],
            )

        monkeypatch.setattr(
            "server.services.planning.planner.plan_steps", _fake_plan_steps
        )

        from server.services.planning.router import process_query

        response = process_query("打开浏览器下载微信安装程序")

        assert planner_calls == ["打开浏览器下载微信安装程序"]
        assert response.detection_meta == {
            "backend": "uia_execution",
            "route": "L3",
            "complexity": 67,
            "omniparser": "not_required",
        }  # 手算：int(13×0.3 + 3×8 + 4×10) = 67
        assert [s.instruction for s in response.steps] == [
            "打开浏览器",
            "下载微信安装程序",
        ]


class TestL2SkipsOmniParser:
    def test_l2_skips_omni_even_with_image(self, monkeypatch):
        """L2 快路径：即使 OmniParser 启用且携带截图，也不做感知扫描。"""
        monkeypatch.setattr(settings, "OMNIPARSER_ENABLED", True)
        omni_calls = []

        def _spy_parse(image_base64, *args, **kwargs):
            omni_calls.append(image_base64)
            raise AssertionError("L2 快路径不应调用 OmniParser")

        monkeypatch.setattr(
            "server.services.omniparser_client.parse_screenshot_full", _spy_parse
        )

        from server.services.planning.router import process_query

        response = process_query(
            "打开计算器", image_base64="data:image/png;base64,QUJD"
        )

        assert omni_calls == []
        assert response.detection_meta == {
            "backend": "template",
            "route": "L2",
            "complexity": 9,
        }


class TestL3UsesOmniParser:
    def test_l3_with_image_scans_omni_when_enabled(self, monkeypatch):
        """L3 正向往证：启用感知且有截图时，真实调用 OmniParser 并吸收其 meta。"""
        from types import SimpleNamespace

        monkeypatch.setattr(settings, "OMNIPARSER_ENABLED", True)
        omni_calls = []

        def _fake_parse(image_base64, *args, **kwargs):
            omni_calls.append(image_base64)
            return SimpleNamespace(
                elements=[],
                annotated_image=None,
                detection_meta={
                    "latency_ms": 5,
                    "element_count": 0,
                    "backend": "local_omniparser",
                },
            )

        monkeypatch.setattr(
            "server.services.omniparser_client.parse_screenshot_full", _fake_parse
        )

        from server.models.schemas import PlanningStep
        from server.services.planning.planner import PlanningResult

        monkeypatch.setattr(
            "server.services.planning.planner.plan_steps",
            lambda q, max_retries=2: PlanningResult(
                goal=q, steps=[PlanningStep(step_index=1, instruction=q)]
            ),
        )

        from server.services.planning.router import process_query

        response = process_query(
            "打开浏览器下载微信安装程序", image_base64="data:image/png;base64,QUJD"
        )

        assert omni_calls == ["data:image/png;base64,QUJD"]
        assert response.annotated_image == "data:image/png;base64,QUJD"
        assert response.detection_meta["latency_ms"] == 5
        assert response.detection_meta["backend"] == "local_omniparser"
        assert response.detection_meta["route"] == "L3"


class TestL2Persistence:
    """缝 S2：TaskRepository 持久化与 L2/L3 统计（in-memory SQLite）。"""

    def test_plan_type_complexity_and_stats(self, monkeypatch):
        """L2 与降级 L3 各一单：plan_type/complexity_score 落库，统计口径正确。"""
        from server.models.schemas import PlanningStep
        from server.services.planning.planner import PlanningResult

        def _fake_plan_steps(query, max_retries=2):
            return PlanningResult(
                goal=query,
                steps=[PlanningStep(step_index=1, instruction=query)],
            )

        monkeypatch.setattr(
            "server.services.planning.planner.plan_steps", _fake_plan_steps
        )

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        import server.database.models  # noqa: F401 — 注册全部 ORM 表
        from server.database import Base
        from server.database.repository import TaskRepository
        from server.services.planning.router import process_query

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            resp_l2 = process_query("打开计算器")
            txn_l2 = TaskRepository.create_from_response(resp_l2, "打开计算器", db=db)
            assert txn_l2.plan_type == "L2"
            assert txn_l2.complexity_score == 9

            resp_deg = process_query("安装微信")
            txn_deg = TaskRepository.create_from_response(resp_deg, "安装微信", db=db)
            assert txn_deg.plan_type == "L3"
            assert txn_deg.complexity_score == 29

            stats = TaskRepository.get_stats_overview(db=db)
            assert stats["l2_count"] == 1
            assert stats["l3_count"] == 1
            assert stats["l2_ratio"] == 0.5
        finally:
            db.close()
