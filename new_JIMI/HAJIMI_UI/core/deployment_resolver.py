"""Campus GPU / deployment mode probing for B-end startup hints."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

CAMPUS_PROBE_PORTS = (8010, 18010, 28010)


def probe_campus_a_end(url: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """Probe A-end /api/demo/health. Returns JSON dict or None if unreachable."""
    base = (url or "").strip().rstrip("/")
    if not base:
        return None
    req = urllib.request.Request(f"{base}/api/demo/health", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError, TimeoutError):
        return None


def _find_campus_gpu_url(timeout: float = 2.0) -> Optional[str]:
    for port in CAMPUS_PROBE_PORTS:
        url = f"http://127.0.0.1:{port}"
        health = probe_campus_a_end(url, timeout=timeout)
        if not health or health.get("status") != "ok":
            continue
        if health.get("detector_device") == "cuda":
            return url
    return None


def get_startup_hints(settings: dict) -> List[str]:
    """
    Non-blocking startup hints based on saved deployment mode and probe results.
    Does not modify user settings.
    """
    hints: List[str] = []
    mode = settings.get("deployment_mode", "local")
    a_url = (settings.get("a_end_url") or "").strip().rstrip("/")

    if mode == "intranet":
        health = probe_campus_a_end(a_url) if a_url else None
        if not health or health.get("status") != "ok":
            hints.append(
                "内网 A 端不可达。请检查校园网/VPN 与 SSH 隧道；"
                "本地演示请在系统设置切换为「本地启动」，或设置 HAJIMI_MOCK_ONLY=1。"
            )
        elif health.get("detector_device") == "cuda":
            hints.append(f"校园 GPU 已连接 ({a_url})，检测将使用远程 cuda。")
        else:
            hints.append(f"内网 A 端已连接 ({a_url})。")
        return hints

    campus_url = _find_campus_gpu_url()
    if campus_url:
        hints.append(
            f"检测到校园 GPU 可用 ({campus_url})，"
            "建议在系统设置切换为「内网 API」以获得最快速度。"
        )
    return hints
