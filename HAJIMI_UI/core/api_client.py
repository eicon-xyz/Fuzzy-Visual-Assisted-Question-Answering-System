"""L5 Sidecar (:8011) HTTP 客户端 —— B 端自动执行模式唯一后端。

旧 A 端 (:8010)、OmniParser 探测、L4 process/inspect/relocate 与 Mock 回退
已随 L4 指引模式整体移除。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

import config


class ApiError(Exception):
    """L5 Sidecar API 调用失败（连接、认证或业务错误）"""


def reload_client_config() -> None:
    """user_settings.apply 后刷新本模块对 config 的引用。"""
    config.reload_from_env()


def _l5_api_base_url() -> str:
    return config.L5_API_URL


def _demo_key() -> str:
    return config.DEMO_KEY


def _api_timeout() -> int:
    return config.API_TIMEOUT


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    reason = getattr(exc, "reason", None)
    return isinstance(reason, TimeoutError) or "timed out" in str(exc).lower()


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            detail = data.get("detail") or (data.get("error") or {}).get("message")
            if detail:
                return str(detail)[:300]
    except Exception:
        pass
    return body[:300] or exc.reason or ""


def _fetch_l5_health_live() -> Optional[dict]:
    """L5 Sidecar (:8011) 轻量存活探测；无 /health/live 时回退 /health。"""
    base = _l5_api_base_url().rstrip("/")
    for path in ("/api/demo/health/live", "/api/demo/health"):
        req = urllib.request.Request(f"{base}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=config.HEALTH_TIMEOUT) as resp:
                if resp.status not in (200, 503):
                    continue
                data = json.loads(resp.read().decode("utf-8"))
                if path.endswith("/health") and resp.status == 503:
                    return {"status": "ok", "degraded": True, **data}
                return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            if exc.code == 503:
                try:
                    data = json.loads(exc.read().decode("utf-8"))
                except Exception:
                    data = {}
                return {"status": "ok", "degraded": True, **data}
        except Exception:
            continue
    return None


def check_l5_health() -> bool:
    """探测 L5 Sidecar (server_A :8011) 是否可用。"""
    live = _fetch_l5_health_live()
    return bool(live and live.get("status") in ("ok", "degraded"))


def fetch_l5_health() -> Optional[dict]:
    """GET L5 Sidecar /api/demo/health，不可用时返回 None。"""
    base = _l5_api_base_url().rstrip("/")
    req = urllib.request.Request(f"{base}/api/demo/health", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=config.HEALTH_TIMEOUT + 2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def get_api_status_message() -> tuple[str, str]:
    """状态栏文案：L5 Sidecar 连接情况。"""
    live = _fetch_l5_health_live()
    if live and live.get("status") == "ok":
        return (f"L5 自动执行就绪 (Sidecar :{config.L5_DEFAULT_PORT})", "system ok")
    if live and live.get("status") in ("degraded", "warn"):
        msg = live.get("message") or "Sidecar 降级：模型未完全就绪"
        return (f"L5 Sidecar 降级 — {msg}", "system warn")
    return (
        f"L5 Sidecar 未启动 (:{config.L5_DEFAULT_PORT})。请运行 {config.L5_START_HINT}",
        "system danger",
    )


def get_api_status_with_connection() -> tuple[str, str, bool]:
    text, msg_type = get_api_status_message()
    return text, msg_type, check_l5_health()


def _request_json(
    path: str,
    payload: Optional[dict] = None,
    *,
    method: str = "POST",
    timeout: Optional[int] = None,
) -> dict:
    root = _l5_api_base_url().rstrip("/")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "X-Demo-Key": _demo_key()}
    req = urllib.request.Request(
        f"{root}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or _api_timeout()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ApiError("X-Demo-Key 不匹配，请检查 HAJIMI_DEMO_KEY") from exc
        raise ApiError(f"L5 Sidecar HTTP {exc.code}: {_read_http_error(exc)}") from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        if _is_timeout_error(exc):
            raise ApiError(f"L5 Sidecar 请求超时（{timeout or _api_timeout()}s）") from exc
        raise ApiError(
            f"L5 Sidecar 不可达 ({getattr(exc, 'reason', exc)})。请先运行: {config.L5_START_HINT}"
        ) from exc


def _ensure_l5_ready() -> tuple[bool, str]:
    """L5 路径：预检 :8011 Sidecar，失败时尝试 auto-launch。"""
    if check_l5_health():
        return True, ""
    try:
        from core.l5_sidecar_launcher import ensure_l5_sidecar_running

        return ensure_l5_sidecar_running()
    except Exception as exc:
        return False, f"L5 Sidecar 不可用: {exc}"


def execute_task(
    query: str,
    image_data_uri: Optional[str] = None,
    *,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> dict:
    """L5：提交自动执行任务到 server_A Sidecar (:8011)，返回 plan + task_id。"""
    ok, reason = _ensure_l5_ready()
    if not ok:
        raise ApiError(reason or f"L5 Sidecar 未就绪，请先运行: {config.L5_START_HINT}")

    try:
        from core.env_sync import sync_l5_sidecar_env
        from core.user_settings import load_user_settings

        sync_l5_sidecar_env(load_user_settings())
    except Exception as exc:
        print(f"[L5] sync_l5_sidecar_env skipped: {exc}")

    from core.l5_query_normalize import normalize_l5_execute_query

    normalized_query = normalize_l5_execute_query(query)
    if normalized_query != query.strip():
        print(f"[L5] query normalized: {query!r} -> {normalized_query!r}")

    payload: dict = {
        "query": normalized_query,
        "image": image_data_uri,
        "context": [],
        "screen_width": screen_width,
        "screen_height": screen_height,
    }
    data = _request_json("/api/demo/execute", payload, timeout=config.EXECUTE_TIMEOUT)
    if not data.get("success"):
        err = data.get("error") or {}
        if isinstance(err, dict):
            raise ApiError(err.get("message") or "L5 执行提交失败")
        raise ApiError("L5 执行提交失败")
    if not data.get("task_id"):
        raise ApiError("L5 Sidecar 未返回 task_id")
    data["_source"] = "l5_sidecar"
    return data


def cancel_task(task_id: str) -> dict:
    """L5：取消进行中的自动执行任务（Sidecar :8011）。"""
    return _request_json(
        "/api/demo/cancel",
        {"task_id": task_id},
        timeout=min(_api_timeout(), 30),
    )
