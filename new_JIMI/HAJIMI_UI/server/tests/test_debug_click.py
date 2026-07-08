"""Tests for POST /api/demo/debug/click — mock click_at, no real pyautogui."""

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

    def test_invalid_coords_422(self, client):
        r = client.post(
            "/api/demo/debug/click",
            json={"x": -1, "y": 200},
            headers=_headers(),
        )
        assert r.status_code == 422

    @patch("server.routes.demo.click_at")
    def test_click_ok(self, mock_click_at, client):
        mock_click_at.return_value = {
            "success": True,
            "x": 960,
            "y": 540,
            "button": "left",
            "clicks": 1,
        }
        r = client.post(
            "/api/demo/debug/click",
            json={"x": 960, "y": 540, "clicks": 1, "button": "left"},
            headers=_headers(),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["x"] == 960
        assert data["y"] == 540
        mock_click_at.assert_called_once_with([960, 540], button="left", clicks=1)

    @patch("server.routes.demo.click_at")
    def test_double_click(self, mock_click_at, client):
        mock_click_at.return_value = {
            "success": True,
            "x": 80,
            "y": 80,
            "button": "left",
            "clicks": 2,
        }
        r = client.post(
            "/api/demo/debug/click",
            json={"x": 80, "y": 80, "clicks": 2},
            headers=_headers(),
        )
        assert r.status_code == 200
        mock_click_at.assert_called_once_with([80, 80], button="left", clicks=2)
