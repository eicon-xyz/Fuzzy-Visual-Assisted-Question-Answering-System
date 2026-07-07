"""L5 Sidecar (new_JIMI :8011) auto-launch orchestrator."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from config import (
    AUTO_LAUNCH_L5,
    L5_DEFAULT_PORT,
    L5_API_URL,
    STARTUP_HEALTH_MAX_RETRIES,
    STARTUP_HEALTH_RETRY_MS,
)
from core.api_client import check_l5_health
from core.service_manager import resolve_l5_root, start_l5_sidecar_window, stop_port

_lock = threading.Lock()
_auto_started = False


def is_l5_auto_started() -> bool:
    with _lock:
        return _auto_started


def _l5_port() -> int:
    try:
        parsed = urlparse(L5_API_URL)
        if parsed.port:
            return parsed.port
    except Exception:
        pass
    return L5_DEFAULT_PORT


def _poll_l5_health_until_ready(timeout_seconds: float = 15.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if check_l5_health():
            return True
        time.sleep(2.0)
    return False


def ensure_l5_sidecar_running(
    progress_callback: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str]:
    """Ensure new_JIMI L5 Sidecar on :8011 is reachable; auto-start if configured."""
    if check_l5_health():
        return True, ""

    if _poll_l5_health_until_ready(4.0):
        return True, ""

    if not AUTO_LAUNCH_L5:
        return False, f"L5 Sidecar 未启动，请运行 scripts\\start_l5_sidecar.bat（{_l5_port()}）"

    l5_root = resolve_l5_root()
    if not l5_root.is_dir():
        return False, (
            f"找不到 new_JIMI Sidecar 目录: {l5_root}\n"
            "请设置 HAJIMI_L5_ROOT 或确认仓库含 new_JIMI/HAJIMI_UI"
        )

    if progress_callback:
        try:
            progress_callback("正在启动 L5 Sidecar (8011)…")
        except Exception:
            pass

    try:
        start_l5_sidecar_window()
    except FileNotFoundError:
        return False, "找不到 scripts\\start_l5_sidecar.bat"
    except Exception as exc:
        return False, f"启动 L5 Sidecar 失败: {exc}"

    with _lock:
        global _auto_started
        _auto_started = True

    time.sleep(3.0)

    for attempt in range(1, STARTUP_HEALTH_MAX_RETRIES + 1):
        if check_l5_health():
            if progress_callback:
                try:
                    progress_callback("L5 Sidecar 已就绪")
                except Exception:
                    pass
            return True, ""

        if attempt < STARTUP_HEALTH_MAX_RETRIES:
            time.sleep(STARTUP_HEALTH_RETRY_MS / 1000.0)

    return (
        False,
        "L5 Sidecar 启动超时。请检查 HAJIMI-L5-Sidecar 终端是否有报错，"
        f"或手动在 new_JIMI 目录运行 start_server.bat（端口 {_l5_port()}）。",
    )


def stop_auto_started_l5_sidecar() -> None:
    """Stop L5 Sidecar if auto-started by this B-end session."""
    with _lock:
        global _auto_started
        if not _auto_started:
            return
        _auto_started = False

    port = _l5_port()
    try:
        killed = stop_port(port)
    except Exception:
        killed = []
    if killed:
        print(f"[l5_sidecar_launcher] stopped auto-started L5 Sidecar on :{port} (PIDs {killed})")
