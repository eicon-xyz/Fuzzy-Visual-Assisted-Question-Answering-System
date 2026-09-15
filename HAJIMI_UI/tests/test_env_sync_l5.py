# -*- coding: utf-8 -*-
"""L5 Sidecar .env sync into server_A (user settings authoritative).

L4/旧 A 端已删除：仅验证 server_A/server/.env 同步行为。
"""
from __future__ import annotations

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


def test_sync_l5_prefers_user_settings(l5_layout):
    out = env_sync.sync_l5_sidecar_env(
        {
            "demo_key": "hajimi-demo-2026",
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
    assert "HAJIMI_PORT=8011" in text
    assert "HAJIMI_DEMO_KEY=hajimi-demo-2026" in text


def test_sync_l5_keeps_existing_sidecar_keys_when_settings_empty(l5_layout):
    env_path = l5_layout / "server" / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=deepseek",
                "LLM_API_KEY=sk-sidecar",
                "LLM_BASE_URL=https://api.deepseek.com",
                "LLM_MODEL=deepseek-chat",
                "OMNIPARSER_ENABLED=false",
                "HAJIMI_DEMO_KEY=hajimi-demo-2026",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out = env_sync.sync_l5_sidecar_env(
        {
            "demo_key": "hajimi-demo-2026",
            "llm": {"api_key": "", "base_url": "", "model": ""},
        }
    )
    assert out is not None
    text = out.read_text(encoding="utf-8")
    # 空设置不得清空 Sidecar 已有模型配置
    assert "LLM_API_KEY=sk-sidecar" in text
    assert "LLM_MODEL=deepseek-chat" in text
    # 非同步键必须原样保留
    assert "OMNIPARSER_ENABLED=false" in text


def test_l5_updates_bind_sidecar_local_8011(l5_layout):
    updates = env_sync._settings_to_l5_updates(
        {
            "demo_key": "hajimi-demo-2026",
            "llm": {"api_key": "sk", "base_url": "https://x/v1", "model": "m"},
        }
    )
    assert updates["HAJIMI_HOST"] == "127.0.0.1"
    assert updates["HAJIMI_PORT"] == "8011"
    assert updates["HAJIMI_DEMO_KEY"] == "hajimi-demo-2026"


def test_sync_without_sidecar_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("HAJIMI_L5_ROOT", str(tmp_path / "nowhere"))
    assert env_sync.sync_l5_sidecar_env({"demo_key": "x"}) is None
