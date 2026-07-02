"""Deploy / operate group2 GPU container for HAJIMI."""
from __future__ import annotations

import argparse
import os
import sys
import tarfile
import tempfile
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parent.parent
HOST = os.environ.get("HAJIMI_GPU_HOST", "10.246.2.7")
PORT = int(os.environ.get("HAJIMI_GPU_SSH_PORT", "12202"))
USER = os.environ.get("HAJIMI_GPU_USER", "student")
PASSWORD = os.environ.get("HAJIMI_GPU_SSH_PASSWORD", "group2-ssh-123")
REMOTE_ROOT = os.environ.get("HAJIMI_GPU_REMOTE", "/workspace/code/HAJIMI_UI")

EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    "server/.venv",
    "node_modules",
    ".cursor",
    "ui/native/_baseline",
    "OmniParser",
}
EXCLUDE_FILES = {".env"}


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=30)
    return client


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 600) -> tuple[int, str, str]:
    print(f"\n>>> {cmd}")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(err.rstrip(), file=sys.stderr)
    return code, out, err


def upload_project(client: paramiko.SSHClient) -> None:
    run(client, f"mkdir -p {REMOTE_ROOT}")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tar_path = tmp.name
    try:
        with tarfile.open(tar_path, "w:gz") as tar:
            for path in ROOT.rglob("*"):
                rel = path.relative_to(ROOT)
                parts = set(rel.parts)
                if parts & EXCLUDE_DIRS:
                    continue
                if any(p in EXCLUDE_DIRS for p in rel.parts):
                    continue
                if path.name in EXCLUDE_FILES and "server" in rel.parts:
                    continue
                if path.is_file() and path.stat().st_size > 50 * 1024 * 1024:
                    continue
                tar.add(path, arcname=str(rel).replace("\\", "/"))
        sftp = client.open_sftp()
        remote_tar = f"{REMOTE_ROOT}/.deploy_upload.tar.gz"
        sftp.put(tar_path, remote_tar)
        sftp.close()
        run(
            client,
            f"cd {REMOTE_ROOT} && tar -xzf .deploy_upload.tar.gz && rm -f .deploy_upload.tar.gz",
            timeout=300,
        )
    finally:
        os.unlink(tar_path)


def upload_server_env(client: paramiko.SSHClient) -> bool:
    local_env = ROOT / "server" / ".env"
    if not local_env.is_file():
        print("No local server/.env — will create from .env.example on remote")
        return False
    sftp = client.open_sftp()
    run(client, f"mkdir -p {REMOTE_ROOT}/server")
    sftp.put(str(local_env), f"{REMOTE_ROOT}/server/.env")
    sftp.close()
    print("Uploaded server/.env")
    return True


def deploy(args: argparse.Namespace) -> int:
    client = connect()
    try:
        if args.upload:
            print("Uploading project (may take a few minutes)...")
            upload_project(client)
            upload_server_env(client)

        run(client, "bash -lc " + repr(f"chmod +x {REMOTE_ROOT}/scripts/gpu_group2_container_services.sh 2>/dev/null; true"))

        # Ensure server venv
        if args.setup_server:
            run(
                client,
                f"cd {REMOTE_ROOT}/server && python3 -m venv .venv && "
                f". .venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt",
                timeout=900,
            )
            if not upload_server_env(client):
                run(
                    client,
                    f"cd {REMOTE_ROOT}/server && "
                    f"test -f .env || (cp .env.example .env && echo 'CREATED_ENV_FROM_EXAMPLE')",
                )

        if args.start_omni:
            run(
                client,
                "bash -lc " + repr(f"{REMOTE_ROOT}/scripts/gpu_group2_container_services.sh start-omni"),
                timeout=120,
            )

        if args.start_a:
            run(
                client,
                "bash -lc " + repr(f"{REMOTE_ROOT}/scripts/gpu_group2_container_services.sh start-a"),
                timeout=120,
            )

        run(client, "bash -lc " + repr(f"{REMOTE_ROOT}/scripts/gpu_group2_container_services.sh status"))
        return 0
    finally:
        client.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Deploy HAJIMI to group2 GPU container")
    p.add_argument("--upload", action="store_true", help="Upload project tarball")
    p.add_argument("--setup-server", action="store_true", help="Create server venv and pip install")
    p.add_argument("--start-omni", action="store_true", help="Start OmniParser tmux")
    p.add_argument("--start-a", action="store_true", help="Start A-end tmux")
    p.add_argument("--all", action="store_true", help="upload + setup + start both")
    args = p.parse_args()
    if args.all:
        args.upload = args.setup_server = args.start_omni = args.start_a = True
    if not any([args.upload, args.setup_server, args.start_omni, args.start_a, args.all]):
        p.print_help()
        sys.exit(1)
    sys.exit(deploy(args))


if __name__ == "__main__":
    main()
