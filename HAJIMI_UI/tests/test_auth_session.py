"""Auth session helpers for B-end login."""
from __future__ import annotations

import urllib.error
from unittest.mock import patch

from core.auth_session import (
    DEFAULT_DEMO_PASSWORD,
    DEFAULT_DEMO_USERNAME,
    LOCAL_DEMO_TOKEN_PREFIX,
    clear_session,
    load_session,
    login,
    normalize_login_response,
)


def test_normalize_stub_login_response():
    raw = {"access_token": "tok", "token_type": "bearer", "expires_in": 7200}
    out = normalize_login_response(raw, "admin")
    assert out["access_token"] == "tok"
    assert out["user"]["username"] == "admin"
    assert out["expires_in"] == 7200


def test_normalize_api_auth_wrapped_response():
    raw = {
        "success": True,
        "data": {
            "access_token": "a",
            "refresh_token": "r",
            "expires_in": 1800,
            "user": {"username": "u1", "role": "admin"},
        },
    }
    out = normalize_login_response(raw)
    assert out["access_token"] == "a"
    assert out["refresh_token"] == "r"
    assert out["user"]["username"] == "u1"


def test_login_fallback_local_demo_on_connection_error(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    clear_session()

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        session = login(DEFAULT_DEMO_USERNAME, DEFAULT_DEMO_PASSWORD)

    assert session["access_token"].startswith(LOCAL_DEMO_TOKEN_PREFIX)
    assert session.get("local_demo") is True
    saved = load_session()
    assert saved is not None
    assert saved["access_token"].startswith(LOCAL_DEMO_TOKEN_PREFIX)


def test_login_connection_error_non_demo_credentials_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    clear_session()

    try:
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            login("other", "wrong")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "无法连接 L5 Sidecar" in str(exc)
