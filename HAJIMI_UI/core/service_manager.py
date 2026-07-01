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


def _start_in_new_console(title: str, bat_path: Path) -> None:
    if not bat_path.is_file():
        raise FileNotFoundError(str(bat_path))
    cmd = f'start "{title}" cmd /k "{bat_path}"'
    subprocess.Popen(cmd, shell=True, cwd=str(ROOT))


def start_omniparser_window() -> None:
    _start_in_new_console("HAJIMI-OmniParser", SCRIPTS / "start_omniparser.bat")


def start_a_end_window() -> None:
    _start_in_new_console("HAJIMI-A-end", SCRIPTS / "start_server.bat")


def start_backend_services() -> None:
    """先停旧进程，再在新窗口启动 OmniParser 与 A 端。"""
    stop_backend_services()
    start_omniparser_window()
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
