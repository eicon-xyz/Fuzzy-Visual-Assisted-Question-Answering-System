"""Remote ops on group2 GPU container via SSH (password from env or defaults)."""
from __future__ import annotations

import argparse
import os
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


def run_remote(commands: list[str], timeout: int = 120) -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20)
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
    ]
    return run_remote(cmds)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["phase0", "services"])
    args = p.parse_args()
    if args.action == "phase0":
        sys.exit(phase0_verify())
    sys.exit(check_services())


if __name__ == "__main__":
    main()
