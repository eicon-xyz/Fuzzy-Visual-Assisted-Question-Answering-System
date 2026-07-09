# -*- coding: utf-8 -*-
"""L5 Sidecar .env sync into server_A (user settings authoritative)."""
from __future__ import annotations

from pathlib import Path

import pytest

import core.env_sync as env_sync


@pytest.fixture
def l5_layout(tmp_path, monkeypatch):
    """Fake L5 Sidecar tree under tmp_path."""
    l5_root = tmp_path / "fake_l5"
    (l5_root / "scripts").mkdir(parents=True)
    (l5_root / "scripts" / "start_server.bat").write_text("@echo off\n", encoding="utf-8")
    server_dir = l5_root / "server"
    server_dir.mkdir()
    (server_dir / ".env.example").write_text(
        "LLM_PROVIDER=qwen\nDEEPSEEK_API_KEY=sk\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HAJIMI_L5_ROOT", str(l5_root))
    return l5_root


def test_resolve_l5_env_path(l5_layout):
    path = env_sync.resolve_l5_env_path()
    assert path == l5_layout / "server" / ".env"


def test_sync_l5_prefers_user_settings_over_legacy_8010(l5_layout, monkeypatch):
    """UI LLM settings must win; HAJIMI_UI/server/.env must not override server_A."""
    canonical = env_sync.ENV_PATH
    monkeypatch.setattr(
        env_sync,
        "ENV_PATH",
        l5_layout.parent / "canonical" / "server" / ".env",
    )
    canon_dir = env_sync.ENV_PATH.parent
    canon_dir.mkdir(parents=True)
    env_sync.ENV_PATH.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=deepseek",
                "LLM_API_KEY=sk-from-8010-stale",
                "LLM_BASE_URL=https://stale.example/v1",
                "LLM_MODEL=stale-model",
                "OMNIPARSER_URL=http://127.0.0.1:9800",
                "HAJIMI_DEMO_KEY=hajimi-demo-2026",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out = env_sync.sync_l5_sidecar_env(
        {
            "demo_key": "hajimi-demo-2026",
            "deployment_mode": "gpu_api",
            "routing_mode": "l5",
            "omniparser": {"url": "http://127.0.0.1:9800"},
            "llm": {
                "api_key": "sk-from-ui",
                "base_url": "https://ui.example/v1",
                "model": "ui-model",
            },
        }
    )
    assert out is not None
    text = out.read_text(encoding="utf-8")
    assert "LLM_API_KEY=sk-from-ui" in text
    assert "LLM_BASE_URL=https://ui.example/v1" in text
    assert "LLM_MODEL=ui-model" in text
    assert "sk-from-8010-stale" not in text
    assert "HAJIMI_PORT=8011" in text


def test_l5_sidecar_updates_from_settings(l5_layout, monkeypatch):
    monkeypatch.setattr(env_sync, "ENV_PATH", Path("/nonexistent/.env"))
    updates = env_sync._l5_sidecar_env_updates(
        {
            "demo_key": "hajimi-demo-2026",
            "deployment_mode": "gpu_api",
            "routing_mode": "l5",
            "a_end_url": "http://127.0.0.1:8010",
            "omniparser": {"url": "http://127.0.0.1:9800"},
        }
    )
    assert updates["OMNIPARSER_URL"] == "http://127.0.0.1:9800"
    assert updates["HAJIMI_DEMO_KEY"] == "hajimi-demo-2026"
    assert updates["HAJIMI_PORT"] == "8011"
    assert updates["LLM_PROVIDER"] == "deepseek"


def test_routing_needs_legacy_a_end():
    assert env_sync.routing_needs_legacy_a_end({"routing_mode": "l5"}) is False
    assert env_sync.routing_needs_legacy_a_end({"routing_mode": "balanced"}) is True


def test_sync_backend_env_skips_legacy_for_l5(l5_layout, monkeypatch):
    monkeypatch.setattr(env_sync, "ENV_PATH", Path("/nonexistent/.env"))
    l5_path, legacy = env_sync.sync_backend_env(
        {
            "routing_mode": "l5",
            "deployment_mode": "gpu_api",
            "demo_key": "hajimi-demo-2026",
            "omniparser": {"url": "http://127.0.0.1:9800"},
        }
    )
    assert l5_path is not None
    assert legacy is None
