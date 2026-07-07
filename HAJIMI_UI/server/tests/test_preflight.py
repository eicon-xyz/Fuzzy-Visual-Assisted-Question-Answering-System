"""B 端预检解耦单元测试。"""
from __future__ import annotations

import pytest

from core.routing_config import get_routing_mode, routing_needs_omniparser


class TestRoutingConfig:
    def test_precision_needs_omniparser(self, monkeypatch):
        monkeypatch.setenv("ROUTING_MODE", "precision")
        assert routing_needs_omniparser() is True

    def test_fast_skips_omniparser(self, monkeypatch):
        monkeypatch.setenv("ROUTING_MODE", "fast")
        assert routing_needs_omniparser() is False

    def test_auto_skips_omniparser(self, monkeypatch):
        monkeypatch.setenv("ROUTING_MODE", "auto")
        assert routing_needs_omniparser() is False

    def test_balanced_skips_omniparser(self, monkeypatch):
        monkeypatch.setenv("ROUTING_MODE", "balanced")
        assert routing_needs_omniparser() is False


class TestProcessPreflight:
    def test_l4_mode_skips_omni_probe(self, monkeypatch):
        import core.api_client as api_client

        monkeypatch.setenv("ROUTING_MODE", "fast")
        monkeypatch.setattr(api_client, "USE_MOCK_ONLY", False)
        monkeypatch.setattr(api_client, "_check_a_end_preflight", lambda: (True, ""))
        monkeypatch.setattr(api_client, "_check_llm_preflight", lambda: (True, ""))
        monkeypatch.setattr(
            api_client,
            "_check_omniparser_preflight",
            lambda h: (False, "OmniParser should not be called"),
        )

        ok, msg = api_client.check_process_preflight()
        assert ok is True
        assert msg == ""

    def test_precision_mode_requires_omni(self, monkeypatch):
        import core.api_client as api_client

        monkeypatch.setenv("ROUTING_MODE", "precision")
        monkeypatch.setattr(api_client, "USE_MOCK_ONLY", False)
        monkeypatch.setattr(api_client, "_check_a_end_preflight", lambda: (True, ""))
        monkeypatch.setattr(
            api_client,
            "_check_omniparser_preflight",
            lambda h: (False, "OmniParser 未就绪"),
        )

        ok, msg = api_client.check_process_preflight()
        assert ok is False
        assert "OmniParser" in msg

    def test_l4_fails_without_llm(self, monkeypatch):
        import core.api_client as api_client

        monkeypatch.setenv("ROUTING_MODE", "auto")
        monkeypatch.setattr(api_client, "USE_MOCK_ONLY", False)
        monkeypatch.setattr(api_client, "_check_a_end_preflight", lambda: (True, ""))
        monkeypatch.setattr(
            api_client,
            "_check_llm_preflight",
            lambda: (False, "L4 需要 LLM"),
        )

        ok, msg = api_client.check_process_preflight()
        assert ok is False
        assert "LLM" in msg

    def test_inspect_always_requires_omni(self, monkeypatch):
        import core.api_client as api_client

        monkeypatch.setenv("ROUTING_MODE", "fast")
        monkeypatch.setattr(api_client, "USE_MOCK_ONLY", False)
        monkeypatch.setattr(api_client, "_check_a_end_preflight", lambda: (True, ""))
        monkeypatch.setattr(
            api_client,
            "_check_omniparser_preflight",
            lambda h: (False, "GPU OmniParser 隧道未就绪"),
        )

        ok, msg = api_client.check_inspect_preflight()
        assert ok is False
        assert "OmniParser" in msg

    def test_ensure_process_auto_starts_a_end_for_l4(self, monkeypatch):
        import core.api_client as api_client

        calls = {"preflight": 0}

        def fake_preflight():
            calls["preflight"] += 1
            if calls["preflight"] == 1:
                return False, "A 端未启动"
            return True, ""

        monkeypatch.setenv("ROUTING_MODE", "fast")
        monkeypatch.setattr(api_client, "check_process_preflight", fake_preflight)
        monkeypatch.setattr(api_client, "_check_a_end_preflight", lambda: (False, "A 端未启动"))
        monkeypatch.setattr(
            "core.service_manager.ensure_a_end_running",
            lambda wait_timeout=30.0: True,
        )

        ok, msg = api_client._ensure_process_ready()
        assert ok is True
        assert calls["preflight"] == 2
