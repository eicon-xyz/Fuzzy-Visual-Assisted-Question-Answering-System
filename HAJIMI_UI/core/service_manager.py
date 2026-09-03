"""Windows 后端服务进程管理：L5 Sidecar (:8011) 按端口停止 / 新窗口启动。

L4/旧 A 端 (:8010) 与 OmniParser (:8002/:9800) 管理已随 L4 指引模式移除。
"""
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
except Exception:
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


def stop_backend_services(l5_port: int | None = None) -> Dict[str, List[int]]:
    """停止 L5 Sidecar（按端口）。"""
    if l5_port is None:
        l5_port = _DEFAULT_L5_PORT
    return {"l5_sidecar": stop_port(l5_port)}


def _start_in_new_console(title: str, bat_path: Path, env_prefix: str = "") -> None:
    if not bat_path.is_file():
        raise FileNotFoundError(str(bat_path))
    cmd = f'{env_prefix}start "{title}" cmd /k "{bat_path}"'
    subprocess.Popen(cmd, shell=True, cwd=str(ROOT))


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


def restart_l5_sidecar() -> None:
    """Stop and restart server_A L5 Sidecar (:8011) to load new server/.env."""
    stop_port(_DEFAULT_L5_PORT)
    start_l5_sidecar_window()


def run_gpu_one_click_bat() -> None:
    """启动全栈（L5 自动执行模式）。委托给 start_release_fullstack.bat。"""
    bat = SCRIPTS / "start_release_fullstack.bat"
    if not bat.is_file():
        raise FileNotFoundError(str(bat))
    subprocess.Popen(f'start "HAJIMI-FullStack" cmd /k "{bat}"', shell=True, cwd=str(ROOT))


def format_stop_summary(result: Dict[str, List[int]], l5_port: int | None = None) -> str:
    if l5_port is None:
        l5_port = _DEFAULT_L5_PORT
    l5 = result.get("l5_sidecar") or []
    if l5:
        return f"L5 Sidecar PID {l5} 已停止"
    return f"L5 Sidecar :{l5_port} 无监听"
