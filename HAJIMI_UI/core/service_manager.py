"""Windows 后端服务进程管理：按端口停止 / 新窗口启动 OmniParser 与 A 端。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

try:
    from config import L5_DEFAULT_PORT as _DEFAULT_L5_PORT
    from config import SERVER_DEFAULT_PORT as _DEFAULT_A_PORT
except Exception:
    _DEFAULT_A_PORT = 8010
    _DEFAULT_L5_PORT = 8011


def _is_windows() -> bool:
    return sys.platform == "win32"


def find_port_pids(port: int) -> List[int]:
    """返回监听指定 TCP 端口的 PID 列表（去重）。"""
    if not _is_windows():
        return []
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return []

    needle = f":{port}"
    pids: List[int] = []
    seen = set()
    for line in out.splitlines():
        if "LISTENING" not in line or needle not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid <= 0 or pid in seen:
            continue
        seen.add(pid)
        pids.append(pid)
    return pids


def kill_pid(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    for args in (
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        ["taskkill", "/F", "/PID", str(pid)],
    ):
        try:
            r = subprocess.run(args, capture_output=True, text=True)
            if r.returncode == 0:
                return True
        except Exception:
            pass
    return False


def stop_port(port: int) -> List[int]:
    """停止占用端口的进程，返回已成功结束的 PID。"""
    killed: List[int] = []
    for pid in find_port_pids(port):
        if kill_pid(pid):
            killed.append(pid)
    return killed


def resolve_l5_root() -> Path:
    """server_A Sidecar 根目录；HAJIMI_L5_ROOT 可覆盖。"""
    from core.paths import resolve_l5_root as _resolve

    return _resolve()


def stop_backend_services(
    a_port: int | None = None,
    omni_port: int = 8002,
    l5_port: int | None = None,
) -> Dict[str, List[int]]:
    """停止 A 端、L5 Sidecar 与 OmniParser（按端口）。"""
    if a_port is None:
        a_port = _DEFAULT_A_PORT
    if l5_port is None:
        l5_port = _DEFAULT_L5_PORT
    return {
        "a_end": stop_port(a_port),
        "l5_sidecar": stop_port(l5_port),
        "omniparser": stop_port(omni_port),
    }


def _resolve_omni_py() -> str:
    omni_py = os.environ.get("OMNI_PY", "")
    if omni_py and Path(omni_py).is_file():
        return omni_py
    for candidate in (
        Path(r"E:\CodingSoftwards\Anaconda\envs\omni\python.exe"),
    ):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def _local_omni_device() -> str:
    script = SCRIPTS / "detect_omni_device.py"
    if not script.is_file():
        return "cpu"
    py = _resolve_omni_py()
    try:
        r = subprocess.run(
            [py, str(script)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        device = (r.stdout or "").strip().lower()
        return device if device in ("cpu", "cuda") else "cpu"
    except Exception:
        return "cpu"


def _start_in_new_console(title: str, bat_path: Path, env_prefix: str = "") -> None:
    if not bat_path.is_file():
        raise FileNotFoundError(str(bat_path))
    cmd = f'{env_prefix}start "{title}" cmd /k "{bat_path}"'
    subprocess.Popen(cmd, shell=True, cwd=str(ROOT))


def is_remote_omni_url(url: str) -> bool:
    """True when OmniParser is remote GPU API (e.g. SSH tunnel :9800)."""
    text = (url or "").strip().rstrip("/")
    return text.endswith(":9800") or ":9800/" in text


def start_omniparser_window() -> None:
    env_prefix = ""
    try:
        from core.user_settings import load_user_settings

        if load_user_settings().get("deployment_mode") == "local":
            if _local_omni_device() == "cpu":
                env_prefix = "set OMNI_FORCE_CPU=1&& "
    except Exception:
        pass
    _start_in_new_console("HAJIMI-OmniParser", SCRIPTS / "start_omniparser.bat", env_prefix)


def start_a_end_window() -> None:
    _start_in_new_console("HAJIMI-A-end", SCRIPTS / "start_server.bat")


def start_l5_sidecar_window() -> None:
    _start_in_new_console("HAJIMI-L5-Sidecar", SCRIPTS / "start_l5_sidecar.bat")


def wait_l5_sidecar_live(timeout_sec: float = 30.0, poll_sec: float = 1.5) -> bool:
    """轮询 L5 Sidecar 进程是否已监听（优先 /health/live，回退 /health）。"""
    base = f"http://127.0.0.1:{_DEFAULT_L5_PORT}"
    paths = ("/api/demo/health/live", "/api/demo/health")
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        for path in paths:
            url = f"{base}{path}"
            try:
                with urllib.request.urlopen(url, timeout=3) as resp:
                    if resp.status in (200, 503):
                        if path.endswith("/health/live"):
                            data = json.loads(resp.read().decode("utf-8"))
                            if data.get("status") == "ok":
                                return True
                        else:
                            return True
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                if exc.code == 503:
                    return True
            except Exception:
                pass
        time.sleep(poll_sec)
    return False


def wait_a_end_live(timeout_sec: float = 30.0, poll_sec: float = 1.5) -> bool:
    """轮询 /api/demo/health/live，确认 A 端 FastAPI 已就绪。"""
    try:
        from config import SERVER_DEFAULT_PORT
    except Exception:
        SERVER_DEFAULT_PORT = _DEFAULT_A_PORT  # type: ignore[misc, assignment]

    url = f"http://127.0.0.1:{SERVER_DEFAULT_PORT}/api/demo/health/live"
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("status") == "ok":
                        return True
        except Exception:
            pass
        time.sleep(poll_sec)
    return False


def ensure_a_end_running(wait_timeout: float = 30.0) -> bool:
    """L4 等轻量模式：端口无监听则启动 A 端并等待 /health/live。"""
    if not _is_windows():
        return False
    try:
        from core.user_settings import is_intranet_mode

        if is_intranet_mode():
            return False
    except Exception:
        pass

    if find_port_pids(_DEFAULT_A_PORT):
        return wait_a_end_live(wait_timeout)

    start_a_end_window()
    return wait_a_end_live(wait_timeout)


def restart_local_a_end() -> None:
    """Stop and restart local A-end only (picks up new server/.env)."""
    stop_port(_DEFAULT_A_PORT)
    start_a_end_window()


def restart_l5_sidecar() -> None:
    """Stop and restart server_A L5 Sidecar (:8011) to load new server/.env."""
    stop_port(_DEFAULT_L5_PORT)
    start_l5_sidecar_window()


def start_gpu_api_services() -> None:
    """GPU API mode: local A-end only; OmniParser runs on GPU via :9800 tunnel."""
    stop_port(_DEFAULT_A_PORT)
    start_a_end_window()


def start_backend_services() -> None:
    """先停旧进程，再在新窗口启动 OmniParser 与 A 端（或仅 A 端）。"""
    try:
        from core.user_settings import load_user_settings

        settings = load_user_settings()
        mode = settings.get("deployment_mode", "gpu_api")
        omni_url = (settings.get("omniparser") or {}).get("url", "")
    except Exception:
        mode = "local"
        omni_url = ""

    if mode == "gpu_api" or is_remote_omni_url(omni_url):
        start_gpu_api_services()
        return

    stop_backend_services()
    start_omniparser_window()
    start_a_end_window()


def run_gpu_one_click_bat() -> None:
    """Launch scripts/start_gpu_one_click.bat in a new console."""
    bat = SCRIPTS / "start_gpu_one_click.bat"
    if not bat.is_file():
        raise FileNotFoundError(str(bat))
    subprocess.Popen(f'start "HAJIMI-GPU-OneClick" cmd /k "{bat}"', shell=True, cwd=str(ROOT))


def format_stop_summary(
    result: Dict[str, List[int]], a_port: int | None = None, l5_port: int | None = None
) -> str:
    if a_port is None:
        a_port = _DEFAULT_A_PORT
    if l5_port is None:
        l5_port = _DEFAULT_L5_PORT
    a = result.get("a_end") or []
    l5 = result.get("l5_sidecar") or []
    o = result.get("omniparser") or []
    parts = []
    if a:
        parts.append(f"A 端 PID {a}")
    else:
        parts.append(f"A 端 :{a_port} 无监听")
    if l5:
        parts.append(f"L5 Sidecar PID {l5}")
    else:
        parts.append(f"L5 Sidecar :{l5_port} 无监听")
    if o:
        parts.append(f"OmniParser PID {o}")
    else:
        parts.append("OmniParser :8002 无监听")
    return "；".join(parts)
