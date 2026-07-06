"""Windows 后端服务进程管理：按端口停止 / 新窗口启动 OmniParser 与 A 端。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

try:
    from config import SERVER_DEFAULT_PORT as _DEFAULT_A_PORT
except Exception:
    _DEFAULT_A_PORT = 8010


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


def stop_backend_services(
    a_port: int | None = None, omni_port: int = 8002
) -> Dict[str, List[int]]:
    """停止 A 端与 OmniParser（按端口）。"""
    if a_port is None:
        a_port = _DEFAULT_A_PORT
    return {
        "a_end": stop_port(a_port),
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
    cmd = f'{env_prefix}start "{title}" cmd /k "cd /d \"%~dp0..\" && \"{bat_path}\""'
    subprocess.Popen(cmd, shell=True, cwd=str(ROOT))


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


def start_backend_services() -> None:
    """先停旧进程，再在新窗口启动 A 端。"""
    stop_backend_services()
    start_a_end_window()


def format_stop_summary(
    result: Dict[str, List[int]], a_port: int | None = None
) -> str:
    if a_port is None:
        a_port = _DEFAULT_A_PORT
    a = result.get("a_end") or []
    o = result.get("omniparser") or []
    parts = []
    if a:
        parts.append(f"A 端 PID {a}")
    else:
        parts.append(f"A 端 :{a_port} 无监听")
    if o:
        parts.append(f"OmniParser PID {o}")
    else:
        parts.append("OmniParser :8002 无监听")
    return "；".join(parts)
