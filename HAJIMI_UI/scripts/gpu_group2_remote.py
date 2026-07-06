"""Remote ops on group2 GPU container via SSH (password from env or defaults)."""
from __future__ import annotations

import argparse
import os
import socket
import sys

try:
    import paramiko
except ImportError:
    print("Install paramiko: pip install paramiko", file=sys.stderr)
    sys.exit(1)

HOST = os.environ.get("HAJIMI_GPU_HOST", "10.246.2.7")
PORT = int(os.environ.get("HAJIMI_GPU_SSH_PORT", "12202"))
USER = os.environ.get("HAJIMI_GPU_USER", "student")
PASSWORD = os.environ.get("HAJIMI_GPU_SSH_PASSWORD", "group2-ssh-123")
REMOTE_ROOT = os.environ.get("HAJIMI_GPU_REMOTE", "/workspace/code/HAJIMI_UI")
CONNECT_TIMEOUT = int(os.environ.get("HAJIMI_GPU_SSH_TIMEOUT", "30"))


def _print_connect_help(reason: str) -> None:
    print(f"\n[FAIL] SSH 无法连接 {USER}@{HOST}:{PORT} — {reason}", file=sys.stderr)
    print(
        "\n排查步骤：\n"
        "  1. 确认已连接校园网或学校 VPN（内网 IP 10.246.x.x 仅校内可达）\n"
        f"  2. PowerShell 测试：Test-NetConnection {HOST} -Port {PORT}\n"
        f"     或：ping {HOST}\n"
        f"  3. 手动 SSH：ssh {USER}@{HOST} -p {PORT}\n"
        "  4. 确认小组端口（group2=12202，见 docs/校园GPU与OmniParser环境速查_v2.md）\n"
        "  5. 密码设环境变量：$env:HAJIMI_GPU_SSH_PASSWORD=\"你的密码\"\n"
        "  6. 仍超时 → 容器可能被平台回收，联系指导教师或重登 GPU 实训平台\n",
        file=sys.stderr,
    )


def _probe_tcp(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def connect_ssh(timeout: int | None = None) -> paramiko.SSHClient:
    t = timeout if timeout is not None else CONNECT_TIMEOUT
    print(f"[ssh] connecting {USER}@{HOST}:{PORT} (timeout={t}s) ...")
    if not _probe_tcp(HOST, PORT, timeout=min(5.0, t)):
        _print_connect_help("TCP 端口不可达（多为未连 VPN/校园网，或 IP/端口错误）")
        raise SystemExit(2)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=t)
    except TimeoutError:
        _print_connect_help("SSH 握手超时")
        raise SystemExit(2) from None
    except paramiko.AuthenticationException:
        print(
            f"\n[FAIL] SSH 认证失败（用户 {USER}）。"
            "请检查 HAJIMI_GPU_SSH_PASSWORD 或 校园gpu使用.md 中的密码。",
            file=sys.stderr,
        )
        raise SystemExit(3) from None
    except (OSError, paramiko.SSHException) as exc:
        _print_connect_help(str(exc))
        raise SystemExit(2) from None
    print("[ssh] connected")
    return client


def run_remote(commands: list[str], timeout: int = 120) -> int:
    client = connect_ssh()
    rc = 0
    try:
        for cmd in commands:
            print(f"\n=== {cmd} ===")
            _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            out = stdout.read().decode(errors="replace").strip()
            err = stderr.read().decode(errors="replace").strip()
            exit_status = stdout.channel.recv_exit_status()
            if out:
                print(out)
            if err:
                print(err, file=sys.stderr)
            if exit_status != 0:
                rc = exit_status
    finally:
        client.close()
    return rc


def phase0_verify() -> int:
    cmds = [
        "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader",
        "python3 - <<'PY'\ntry:\n import torch\n print('CUDA:', torch.cuda.is_available())\nexcept Exception as e:\n print('CUDA_CHECK:', e)\nPY",
        "test -d /workspace/code && test -d /workspace/models && echo WORKSPACE_OK || echo WORKSPACE_MISSING",
        "ls -la /workspace/code 2>/dev/null | head -8",
    ]
    return run_remote(cmds)


def check_services() -> int:
    cmds = [
        "curl -s -m 3 http://127.0.0.1:8002/probe/ || echo OMNIPARSER_DOWN",
        "curl -s -m 3 http://127.0.0.1:8010/api/demo/health || echo A_END_DOWN",
        "curl -s -m 3 http://127.0.0.1:9800/health || echo API_9800_DOWN",
    ]
    return run_remote(cmds)


def start_omniparser_api() -> int:
    """Start omniparser_api on :9800 if health check fails."""
    cmd = (
        "curl -sf -m 3 http://127.0.0.1:9800/health >/dev/null && "
        'echo "[9800] already up" || '
        "(cd /workspace/code/omniparser_api && "
        "mkdir -p /workspace/code/HAJIMI_UI/logs && "
        "nohup ./start.sh >> /workspace/code/HAJIMI_UI/logs/omniparser_api.log 2>&1 & "
        "for i in $(seq 1 30); do "
        "curl -sf -m 3 http://127.0.0.1:9800/health >/dev/null && "
        'echo "[9800] ready after ${i}s" && curl -s http://127.0.0.1:9800/health && exit 0; '
        "sleep 2; done; "
        'echo "[9800] not ready"; exit 1)'
    )
    rc = run_remote([f"bash -lc {repr(cmd)}"], timeout=180)
    if rc != 0:
        return rc
    return run_remote(["curl -s -m 5 http://127.0.0.1:9800/health || echo API_9800_DOWN"])


def start_all_services() -> int:
    script = f"{REMOTE_ROOT}/scripts/gpu_group2_container_services.sh"
    rc = run_remote([f"bash -lc {repr(f'chmod +x {script} 2>/dev/null; {script} start-all')}"], timeout=360)
    if rc != 0:
        return rc
    return check_services()


def main() -> None:
    p = argparse.ArgumentParser(description="Remote ops on group2 GPU container via SSH")
    p.add_argument(
        "action",
        choices=["phase0", "services", "start-all", "start-9800"],
        help="phase0=GPU check; services=probe health; start-all=remote start Omni+A; start-9800=omniparser_api :9800",
    )
    args = p.parse_args()
    if args.action == "phase0":
        sys.exit(phase0_verify())
    if args.action == "start-all":
        sys.exit(start_all_services())
    if args.action == "start-9800":
        sys.exit(start_omniparser_api())
    sys.exit(check_services())


if __name__ == "__main__":
    main()
