"""A-end auto-launch orchestrator.

When B-end detects A-end is not running, this module can automatically
launch it in a new console window and poll until healthy — so the user
doesn't need to manually run ``scripts\\start_server.bat``.

Exported functions
------------------
ensure_a_end_running(progress_callback=None) -> tuple[bool, str]
    Check health; if unhealthy and auto-launch is enabled, start A-end
    and block-poll until ready or timeout.
stop_auto_started_a_end() -> None
    Stop the A-end process that *this* B-end session auto-started.
is_auto_started() -> bool
    Return whether this session auto-started A-end.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from config import (
    API_BASE_URL,
    AUTO_LAUNCH_A_END,
    DEPLOYMENT_MODE,
    SERVER_DEFAULT_PORT,
    STARTUP_HEALTH_DELAY_MS,
    STARTUP_HEALTH_MAX_RETRIES,
    STARTUP_HEALTH_RETRY_MS,
)
from core.api_client import check_health
from core.service_manager import start_a_end_window, stop_port

# How many times to poll health before giving up.
_POLL_MAX_RETRIES = STARTUP_HEALTH_MAX_RETRIES
_POLL_RETRY_S = STARTUP_HEALTH_RETRY_MS / 1000.0

_lock = threading.Lock()
_auto_started = False


def is_auto_started() -> bool:
    """Return True if this B-end session auto-started the A-end process."""
    with _lock:
        return _auto_started


def _a_end_port() -> int:
    """Extract A-end port from the configured API URL."""
    try:
        parsed = urlparse(API_BASE_URL)
        if parsed.port:
            return parsed.port
        if parsed.scheme == "https":
            return 443
    except Exception:
        pass
    return SERVER_DEFAULT_PORT


def _poll_health_until_ready(timeout_seconds: float = 15.0) -> bool:
    """Poll health check until A-end is ready or timeout.

    This is used BEFORE starting a new A-end — if start_all.bat already
    launched one, we wait for it instead of killing and restarting.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if check_health():
            return True
        time.sleep(2.0)
    return False


def ensure_a_end_running(
    progress_callback: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str]:
    """Make sure A-end is reachable, auto-starting it if configured.

    Parameters
    ----------
    progress_callback:
        Called with a human-readable status string (e.g. "正在启动 A 端…")
        so callers can forward progress to their UI.

    Returns
    -------
    (ok, message):
        ``ok`` is True when A-end is healthy (was already, or just started).
        ``message`` is empty on success, or a Chinese reason on failure.
    """
    # 1. Already healthy — nothing to do.
    if check_health():
        return True, ""

    # 1b. Quick retry — A-end may be mid-initialization

    # 2. Intranet mode — can't auto-start a remote server.
    if DEPLOYMENT_MODE == "intranet":
        return False, "内网模式下无法自动启动 A 端，请确认校园网/VPN 与地址是否正确。"

    # 3. Feature disabled by user.
    if not AUTO_LAUNCH_A_END:
        return False, ""

    # 4. Wait a bit — start_all.bat may have just launched A-end.
    #    Also prevents the race where start_server.bat kills a loading A-end.
    if _poll_health_until_ready(4.0):
        return True, ""

    # 5. A-end not reachable — launch it ourselves.
    if progress_callback:
        try:
            progress_callback("正在启动 A 端…")
        except Exception:
            pass

    try:
        start_a_end_window()
    except FileNotFoundError:
        return False, "找不到 scripts\\start_server.bat，请确认 HAJIMI_UI 目录完整。"
    except Exception as exc:
        return False, f"启动 A 端失败: {exc}"

    # 6. Mark that we auto-started it (thread-safe).
    with _lock:
        global _auto_started
        _auto_started = True

    # 7. Poll until ready (faster — was 15s delay)
    time.sleep(3.0)

    for attempt in range(1, STARTUP_HEALTH_MAX_RETRIES + 1):
        if check_health():
            if progress_callback:
                try:
                    progress_callback("A 端已就绪")
                except Exception:
                    pass
            return True, ""

        if attempt < STARTUP_HEALTH_MAX_RETRIES:
            time.sleep(STARTUP_HEALTH_RETRY_MS / 1000.0)

    # 8. Timed out.
    return (
        False,
        "A 端启动超时。请检查弹出的终端窗口是否有报错，"
        f"或手动运行 scripts\\start_server.bat（端口 {_a_end_port()}）。",
    )


def stop_auto_started_a_end() -> None:
    """Stop A-end if it was auto-started by *this* B-end session.

    Safe to call even when nothing was auto-started (no-op).
    Does NOT stop A-end instances that the user started manually.
    """
    with _lock:
        global _auto_started
        if not _auto_started:
            return
        _auto_started = False

    port = _a_end_port()
    try:
        killed = stop_port(port)
    except Exception:
        killed = []
    if killed:
        print(f"[a_end_launcher] stopped auto-started A-end on port {port} (PIDs {killed})")
    else:
        print(f"[a_end_launcher] no A-end process found on port {port} to stop")
