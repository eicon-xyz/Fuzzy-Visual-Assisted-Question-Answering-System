"""B-end login session (local file); demo API still uses X-Demo-Key."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import config

DEFAULT_DEMO_USERNAME = "admin"
DEFAULT_DEMO_PASSWORD = "demo123"
LOCAL_DEMO_TOKEN_PREFIX = "local-demo."
LOCAL_DEMO_EXPIRES_SEC = 7200


def _session_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = Path(base) / "HAJIMI"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "auth_session.json"


def normalize_login_response(raw: dict, fallback_username: str = "") -> dict:
    if raw.get("success") is True and isinstance(raw.get("data"), dict):
        data = raw["data"]
        return {
            "access_token": data.get("access_token") or "",
            "refresh_token": data.get("refresh_token"),
            "user": data.get("user") or {"username": fallback_username, "role": "admin"},
            "expires_in": int(data.get("expires_in") or 1800),
        }
    if raw.get("access_token"):
        return {
            "access_token": raw["access_token"],
            "refresh_token": raw.get("refresh_token"),
            "user": raw.get("user") or {"username": fallback_username, "role": "admin"},
            "expires_in": int(raw.get("expires_in") or 7200),
        }
    raise ValueError("登录响应缺少 access_token")


def load_session() -> Optional[Dict[str, Any]]:
    path = _session_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_session(session: Dict[str, Any]) -> None:
    path = _session_path()
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_session() -> None:
    path = _session_path()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def is_session_valid() -> bool:
    session = load_session()
    if not session or not session.get("access_token"):
        return False
    expires_at = session.get("expires_at")
    if expires_at is None:
        return True
    try:
        return float(expires_at) > time.time()
    except (TypeError, ValueError):
        return False


def get_username() -> str:
    session = load_session() or {}
    user = session.get("user") or {}
    return str(user.get("username") or session.get("username") or DEFAULT_DEMO_USERNAME)


def _is_demo_credentials(username: str, password: str) -> bool:
    return (
        username.strip() == DEFAULT_DEMO_USERNAME
        and password == DEFAULT_DEMO_PASSWORD
    )


def _create_local_demo_session(username: str) -> Dict[str, Any]:
    """Offline demo session when A-end is unreachable (default credentials only)."""
    session = {
        "access_token": f"{LOCAL_DEMO_TOKEN_PREFIX}{int(time.time())}",
        "refresh_token": None,
        "user": {"username": username, "role": "admin"},
        "username": username,
        "expires_at": time.time() + LOCAL_DEMO_EXPIRES_SEC,
        "local_demo": True,
    }
    save_session(session)
    return session


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
        data = json.loads(body)
        detail = data.get("detail")
        if isinstance(detail, dict):
            err = detail.get("error") or detail
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
        if isinstance(detail, str):
            return detail
        if data.get("error", {}).get("message"):
            return str(data["error"]["message"])
        return body[:200] or f"HTTP {exc.code}"
    except Exception:
        return f"HTTP {exc.code}"


def login(username: str, password: str) -> Dict[str, Any]:
    """POST /api/auth/login (no Demo Key). Returns saved session dict."""
    root = config.L5_API_URL.rstrip("/")
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{root}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_read_http_error(exc)) from exc
    except urllib.error.URLError as exc:
        if _is_demo_credentials(username, password):
            return _create_local_demo_session(username.strip())
        raise RuntimeError(
            f"无法连接 L5 Sidecar ({config.L5_API_URL})。请先启动服务或设置 HAJIMI_SKIP_LOGIN=1"
        ) from exc

    normalized = normalize_login_response(raw, username)
    expires_in = int(normalized.get("expires_in") or 7200)
    session = {
        "access_token": normalized["access_token"],
        "refresh_token": normalized.get("refresh_token"),
        "user": normalized.get("user") or {"username": username, "role": "admin"},
        "username": username,
        "expires_at": time.time() + expires_in,
    }
    save_session(session)
    return session


def logout() -> None:
    clear_session()
