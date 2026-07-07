"""Keep local :9800 forwarded to GPU omniparser_api (paramiko, auto password)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from gpu_ssh_tunnel import run_tunnel


def main() -> int:
    run_tunnel(local_port=9800, remote_host="127.0.0.1", remote_port=9800)
    return 0


if __name__ == "__main__":
    sys.exit(main())
