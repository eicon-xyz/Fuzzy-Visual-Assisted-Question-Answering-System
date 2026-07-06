"""Kill all processes listening on a TCP port (Windows). Usage: python scripts/kill_port.py 8001"""
from __future__ import annotations

import subprocess
import sys
import time


def find_pids(port: int) -> list[int]:
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
    pids: list[int] = []
    seen: set[int] = set()
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
        if pid > 0 and pid not in seen:
            seen.add(pid)
            pids.append(pid)
    return pids


def kill_pid(pid: int) -> bool:
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


def kill_port(port: int, retries: int = 3) -> list[int]:
    killed: list[int] = []
    for _ in range(retries):
        pids = find_pids(port)
        if not pids:
            break
        for pid in pids:
            if kill_pid(pid):
                killed.append(pid)
                print(f"[kill_port] :{port} killed PID {pid}")
            else:
                print(f"[kill_port] :{port} failed PID {pid} (may be stale netstat entry)")
        time.sleep(0.5)
    return killed


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/kill_port.py <port>", file=sys.stderr)
        return 2
    try:
        port = int(sys.argv[1])
    except ValueError:
        print(f"Invalid port: {sys.argv[1]}", file=sys.stderr)
        return 2
    killed = kill_port(port)
    remaining = find_pids(port)
    if remaining:
        print(f"[kill_port] WARN :{port} still LISTENING PIDs: {remaining}")
        return 1
    print(f"[kill_port] :{port} is free (killed {len(killed)} process(es))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
