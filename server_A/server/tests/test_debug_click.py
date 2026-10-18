"""POST /api/demo/debug/click —— Phase 1 后它是"默认关闭的调试后门"。

判据：
  1. 默认 403（HID_DEBUG_ALLOWED=false），且**不碰** hid
  2. 显式开启后，走的是与生产同一条 hid 路径（发短期调试许可），不存在
     "绕过许可的点击"
  3. 认证/坐标校验不变
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from server.config import settings
from server.main import app


def _headers():
    return {"X-Demo-Key": settings.DEMO_KEY}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def hid_enabled(monkeypatch):
    monkeypatch.setattr(settings, "HID_DEBUG_ALLOWED", True)
    return True


class TestDebugClick:
    def test_no_key_401(self, client):
        r = client.post("/api/demo/debug/click", json={"x": 100, "y": 200})
        assert r.status_code == 401

    def test_wrong_key_401(self, client):
        r = client.post(
            "/api/demo/debug/click",
            json={"x": 100, "y": 200},
            headers={"X-Demo-Key": "wrong"},
        )
        assert r.status_code == 401

    def test_invalid_coords_422(self, client, hid_enabled):
        r = client.post(
            "/api/demo/debug/click",
            json={"x": -1, "y": 200},
            headers=_headers(),
        )
        assert r.status_code == 422

    def test_disabled_by_default_403(self, client, monkeypatch):
        monkeypatch.setattr(settings, "HID_DEBUG_ALLOWED", False)
        with patch("server.services.executor.hid.click") as mock_click:
            r = client.post(
                "/api/demo/debug/click",
                json={"x": 100, "y": 200},
                headers=_headers(),
            )
        assert r.status_code == 403
        assert r.json()["detail"]["error"]["code"] == "HID_DEBUG_DISABLED"
        mock_click.assert_not_called()

    def test_click_ok_when_enabled(self, client, hid_enabled):
        from server.services.executor.hid import HIDResult

        with patch(
            "server.services.executor.hid.click",
            return_value=HIDResult(
                ok=True,
                detail={"via": "coord", "x": 960, "y": 540, "button": "left", "clicks": 1},
            ),
        ) as mock_click:
            r = client.post(
                "/api/demo/debug/click",
                json={"x": 960, "y": 540, "clicks": 1, "button": "left"},
                headers=_headers(),
            )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["x"] == 960 and data["y"] == 540

        # 第一个位置参数必须是许可（不是 None）——这就是"不存在绕过许可的点击"
        args, kwargs = mock_click.call_args
        permit = args[0]
        assert permit is not None, "调试后门也必须持许可"
        assert permit.task_id == "__debug_click__"
        assert args[1] == (960, 540)
        assert kwargs["clicks"] == 1
        assert kwargs["button"] == "left"

    def test_permit_is_revoked_after_request(self, client, hid_enabled):
        from server.services.executor.hid import HIDResult
        from server.services.executor.permit import BROKER, PermitState

        with patch(
            "server.services.executor.hid.click",
            return_value=HIDResult(ok=True, detail={"via": "coord"}),
        ):
            client.post(
                "/api/demo/debug/click",
                json={"x": 10, "y": 10},
                headers=_headers(),
            )
        assert BROKER.state("__debug_click__") == PermitState.REVOKED
