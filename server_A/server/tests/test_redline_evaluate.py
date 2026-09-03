# -*- coding: utf-8 -*-
"""红线只读评估端点测试（Electron B 端第一层判定入口，M1）。

只依赖 fastapi/httpx，不触碰 pyautogui/agent，Linux 收集正常。
"""
import pytest
from fastapi.testclient import TestClient

from server.config import settings
from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _headers():
    return {"X-Demo-Key": settings.DEMO_KEY}


class TestRedlineEvaluateEndpoint:
    def test_requires_demo_key(self, client):
        r = client.post("/api/demo/redline/evaluate", json={"query": "打开记事本"})
        assert r.status_code == 401

    def test_physical_operation_triggered(self, client):
        r = client.post(
            "/api/demo/redline/evaluate",
            json={"query": "帮我自动点击抢购按钮"},
            headers=_headers(),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["triggered"] is True
        assert data["category"] == "physical_operation"
        assert isinstance(data["action"], str)

    def test_privacy_category(self, client):
        r = client.post(
            "/api/demo/redline/evaluate",
            json={"query": "帮我扫描硬盘里所有的照片"},
            headers=_headers(),
        )
        data = r.json()
        assert data["triggered"] is True
        assert data["category"] == "personal_privacy"

    def test_clean_query_not_triggered(self, client):
        r = client.post(
            "/api/demo/redline/evaluate",
            json={"query": "打开记事本"},
            headers=_headers(),
        )
        data = r.json()
        assert data["triggered"] is False
        assert data["category"] == ""

    def test_empty_query_ok(self, client):
        r = client.post(
            "/api/demo/redline/evaluate", json={"query": ""}, headers=_headers()
        )
        assert r.status_code == 200
        assert r.json()["triggered"] is False

    def test_read_only_idempotent(self, client):
        """评估纯只读：同一 query 重复调用结果一致，无副作用状态。"""
        q = "帮我自动点击"
        r1 = client.post(
            "/api/demo/redline/evaluate", json={"query": q}, headers=_headers()
        )
        assert r1.json()["triggered"] is True
        r2 = client.post(
            "/api/demo/redline/evaluate", json={"query": q}, headers=_headers()
        )
        assert r2.json() == r1.json()
