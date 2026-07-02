"""Fix remote server/.env and restart A-end on group2."""
from __future__ import annotations

import paramiko

HOST, PORT, USER, PW = "10.246.2.7", 12202, "student", "group2-ssh-123"
REMOTE = "/workspace/code/HAJIMI_UI"


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PW, timeout=30)
    cmds = [
        f"grep -E '^DETECTOR_BACKEND=' {REMOTE}/server/.env || echo 'DETECTOR_BACKEND missing'",
        f"sed -i 's/^DETECTOR_BACKEND=.*/DETECTOR_BACKEND=auto/' {REMOTE}/server/.env",
        f"grep DETECTOR_BACKEND {REMOTE}/server/.env",
        "pkill -f 'uvicorn server.main:app' || true",
        "sleep 2",
        f"bash {REMOTE}/scripts/gpu_group2_container_services.sh start-a",
        f"bash {REMOTE}/scripts/gpu_group2_container_services.sh status",
    ]
    for cmd in cmds:
        print(f"\n>>> {cmd}")
        _, o, e = c.exec_command(cmd, timeout=180)
        print(o.read().decode())
        err = e.read().decode()
        if err.strip():
            print(err)
    c.close()


if __name__ == "__main__":
    main()
