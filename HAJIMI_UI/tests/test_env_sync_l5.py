# -*- coding: utf-8 -*-
"""L5 Sidecar .env sync from canonical 8010 server/.env."""
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


def test_sync_l5_sidecar_env_writes_deepseek(l5_layout, monkeypatch):
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
                "DEEPSEEK_API_KEY=sk-test-deepseek",
                "DEEPSEEK_BASE_URL=https://api.deepseek.com",
                "DEEPSEEK_MODEL=deepseek-chat",
                "OMNIPARSER_URL=http://127.0.0.1:9800",
                "HAJIMI_DEMO_KEY=hajimi-demo-2026",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out = env_sync.sync_l5_sidecar_env({"demo_key": "hajimi-demo-2026"})
    assert out is not None
    text = out.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-test-deepseek" in text
    assert "LLM_PROVIDER=deepseek" in text
    assert "OMNIPARSER_URL=http://127.0.0.1:9800" in text


def test_l5_sidecar_updates_from_settings(l5_layout, monkeypatch):
    monkeypatch.setattr(env_sync, "ENV_PATH", Path("/nonexistent/.env"))
    updates = env_sync._l5_sidecar_env_updates(
        {
            "demo_key": "hajimi-demo-2026",
            "deployment_mode": "gpu_api",
            "omniparser": {"url": "http://127.0.0.1:9800"},
        }
    )
    assert updates["OMNIPARSER_URL"] == "http://127.0.0.1:9800"
    assert updates["HAJIMI_DEMO_KEY"] == "hajimi-demo-2026"
    assert updates["LLM_PROVIDER"] == "deepseek"
