"""B 端 repo path bootstrap — client import shadow 修复。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HAJIMI_UI = ROOT / "HAJIMI_UI"
if str(HAJIMI_UI) not in sys.path:
    sys.path.insert(0, str(HAJIMI_UI))


def test_shadow_client_cleared_and_integration_importable():
    """模拟 HAJIMI_UI/client namespace 污染后仍能加载 integration。"""
    ui = str(HAJIMI_UI)
    if ui in sys.path:
        sys.path.remove(ui)
    sys.path.insert(0, ui)
    import client  # noqa: F401 — namespace from HAJIMI_UI/client if present

    from core.repo_paths import clear_shadow_client_modules, ensure_repo_root_on_path

    ensure_repo_root_on_path()
    clear_shadow_client_modules()
    from client.integration.controller import VoiceIntegrationController

    assert VoiceIntegrationController is not None
    assert getattr(client, "__file__", None) is not None


def test_default_audit_db_under_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from client.paths import default_audit_db_path

    path = default_audit_db_path()
    assert path.startswith(str(tmp_path))
    assert path.endswith("audit_queue.db")
