# -*- coding: utf-8 -*-
"""B 端 consent 透传：只有知情确认通过后，才把 takeover_consent 发给 Sidecar。

不变量：``api_client.execute_task`` 默认 **不** 授权（fail-closed）；
``app_controller`` 只有在 ``ensure_l5_consent()`` 返回 True 之后才传 True。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HAJIMI_UI = ROOT / "HAJIMI_UI"
if str(HAJIMI_UI) not in sys.path:
    sys.path.insert(0, str(HAJIMI_UI))

import core.api_client as api_client  # noqa: E402
from core import execute_worker as ew  # noqa: E402


def _capture_execute(monkeypatch) -> dict:
    captured: dict = {}

    def fake_request_json(path, payload=None, *, method="POST", timeout=None):
        captured["path"] = path
        captured["payload"] = payload
        return {"success": True, "task_id": "tid-1"}

    monkeypatch.setattr(api_client, "_ensure_l5_ready", lambda: (True, ""))
    monkeypatch.setattr(api_client, "_request_json", fake_request_json)
    return captured


def test_payload_defaults_to_fail_closed(monkeypatch):
    cap = _capture_execute(monkeypatch)
    api_client.execute_task("打开记事本")
    assert cap["payload"]["takeover_consent"] is False


def test_payload_carries_consent(monkeypatch):
    cap = _capture_execute(monkeypatch)
    api_client.execute_task("打开记事本", takeover_consent=True)
    assert cap["payload"]["takeover_consent"] is True


def test_worker_passes_consent_to_client(monkeypatch):
    seen: dict = {}

    def fake_execute(query, image_data_uri=None, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return {}  # 缺 task_id → run() 报错返回，不会进 SSE

    monkeypatch.setattr(ew, "api_execute_task", fake_execute)
    worker = ew.ExecuteWorkerThread()
    worker.query = "打开记事本"
    worker._consent = True
    worker.run()
    assert seen["kwargs"].get("takeover_consent") is True


def test_worker_defaults_to_no_consent(monkeypatch):
    seen: dict = {}

    def fake_execute(query, image_data_uri=None, **kwargs):
        seen["kwargs"] = kwargs
        return {}

    monkeypatch.setattr(ew, "api_execute_task", fake_execute)
    worker = ew.ExecuteWorkerThread()
    worker.query = "打开记事本"
    worker.run()
    assert seen["kwargs"].get("takeover_consent") is False
