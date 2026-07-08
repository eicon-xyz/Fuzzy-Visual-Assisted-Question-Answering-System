"""B 端 E2E：保持 SSH 隧道并运行 health + verify_integration。"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, ROOT)

import paramiko
from b_group2_intranet_setup import (
    HOST,
    SSH_PORT,
    USER,
    PASSWORD,
    REMOTE_HOST,
    REMOTE_PORT,
    _pick_local_port,
    _start_forward_server,
)
import b_group2_intranet_setup as tunnel_mod


def run_with_tunnel():
    local_port = _pick_local_port()
    base = f"http://127.0.0.1:{local_port}"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=SSH_PORT, username=USER, password=PASSWORD, timeout=20)
    tunnel_mod._transport = client.get_transport()
    server = _start_forward_server(local_port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.8)
    return client, server, base, local_port


def main() -> int:
    from core.user_settings import apply_user_settings, load_user_settings
    from core.api_client import get_api_status_message, check_health

    client, server, base, port = run_with_tunnel()
    os.environ["HAJIMI_API_URL"] = base
    os.environ["HAJIMI_DEPLOYMENT_MODE"] = "intranet"
    apply_user_settings(load_user_settings())

    print(f"[e2e] tunnel localhost:{port} -> {REMOTE_HOST}:{REMOTE_PORT}")
    print(f"[e2e] HAJIMI_API_URL={base}")

    ok = check_health()
    msg, typ = get_api_status_message()
    print(f"[e2e] check_health={ok}")
    print(f"[e2e] status: {msg} ({typ})")

    rc = 0 if ok else 1
    if ok:
        env = os.environ.copy()
        print("[e2e] running verify_integration.py ...")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "verify_integration.py")],
            cwd=ROOT,
            env=env,
        )
        rc = proc.returncode

    server.shutdown()
    client.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
