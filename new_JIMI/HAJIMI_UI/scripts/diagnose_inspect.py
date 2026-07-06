"""
检验模式链路诊断：检查 A 端 /health、OmniParser /probe/、端口占用。

Usage:
  python scripts/diagnose_inspect.py
  python scripts/diagnose_inspect.py --full   # 额外跑 1x1 探针 parse（约 2 分钟，CPU）

启动顺序（任一 FAIL 时）:
  1. scripts\\start_omniparser.bat  → 等到 Omniparser initialized
  2. scripts\\start_server.bat
  3. conda activate videorag && python main.py
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import API_BASE_URL, SERVER_DEFAULT_PORT  # noqa: E402

A_END_PORT = SERVER_DEFAULT_PORT

OMNI_PROBE_URL = "http://127.0.0.1:8002/probe/"
TINY_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _get_json(url: str, timeout: float = 5.0) -> Tuple[bool, dict | str]:
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return True, json.loads(body)
    except URLError as exc:
        return False, str(getattr(exc, "reason", exc))
    except Exception as exc:
        return False, str(exc)


def _port_listeners(port: int) -> List[int]:
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return []
    pids: List[int] = []
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" not in line or needle not in line:
            continue
        parts = line.split()
        if len(parts) >= 5:
            try:
                pids.append(int(parts[-1]))
            except ValueError:
                pass
    return pids


def _probe_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def check_a_end_health() -> Tuple[bool, str]:
    url = f"{API_BASE_URL}/api/demo/health"
    ok, data = _get_json(url)
    if not ok:
        return False, f"A 端不可达 ({url}): {data}"

    if not isinstance(data, dict) or data.get("status") != "ok":
        return False, f"A 端 health 异常: {data}"

    backend = data.get("detector_backend")
    if backend != "local_omniparser":
        return (
            False,
            f"detector_backend={backend!r}，期望 local_omniparser。"
            "请检查 server/.env 并重启 A 端。",
        )

    ready = data.get("omniparser_ready")
    if ready is None:
        return (
            False,
            "health 缺少 omniparser_ready 字段（旧版 A 端）。请重启 scripts\\start_server.bat。",
        )
    if ready is False:
        return False, "omniparser_ready=false，OmniParser 未就绪。"

    return True, f"OK backend={backend} omniparser_ready={ready}"


def check_omniparser_probe() -> Tuple[bool, str]:
    ok, data = _get_json(OMNI_PROBE_URL)
    if not ok:
        return False, f"OmniParser /probe/ 不可达: {data}"
    if isinstance(data, dict) and data.get("message"):
        return True, f"OK {data.get('message')}"
    return True, f"OK {data}"


def check_ports() -> Tuple[bool, str]:
    issues: List[str] = []
    for port, name in ((A_END_PORT, "A-end"), (8002, "OmniParser")):
        pids = _port_listeners(port)
        if not pids:
            issues.append(f":{port} ({name}) 无 LISTENING 进程")
        elif len(pids) > 1:
            issues.append(f":{port} ({name}) 多个 LISTENING PID: {pids}（建议 taskkill 后只留一个）")
        else:
            if not _probe_tcp("127.0.0.1", port):
                issues.append(f":{port} ({name}) netstat 有 PID {pids[0]} 但 TCP 连接失败")
    if issues:
        return False, "; ".join(issues)
    return True, f"OK :{A_END_PORT}/8002 各 1 个 LISTENING 且可连接"


def check_full_parse() -> Tuple[bool, str]:
    import httpx

    print("[diagnose] --full: POST /parse/ with 1x1 PNG (CPU ~2min)...")
    try:
        with httpx.Client(timeout=360.0) as client:
            resp = client.post(
                "http://127.0.0.1:8002/parse/",
                json={"base64_image": TINY_B64},
            )
        if resp.status_code == 200:
            payload = resp.json()
            n = len(payload.get("parsed_content_list") or [])
            return True, f"OK parse status=200 elements={n}"
        return False, f"parse HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="HAJIMI inspect chain diagnostics")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run OmniParser /parse/ with 1x1 PNG (~2min on CPU)",
    )
    args = parser.parse_args()

    checks = [
        ("A-end /health", check_a_end_health),
        ("OmniParser /probe/", check_omniparser_probe),
        ("Ports A-end/OmniParser", check_ports),
    ]
    if args.full:
        checks.append(("OmniParser /parse/ (full)", check_full_parse))

    print("=== HAJIMI inspect diagnostics ===")
    print(f"API_BASE_URL = {API_BASE_URL}")
    print()

    all_ok = True
    for name, fn in checks:
        ok, detail = fn()
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {name}: {detail}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("[OK] 链路就绪。B 端 Settings →「立即检测」只点一次，等待 2–4 分钟。")
        print("     点击后 10 秒内 OmniParser 终端应出现 start parsing...")
        return 0

    print("[FAIL] 请按顺序重启:")
    print("  1. scripts\\start_omniparser.bat   (等到 Omniparser initialized)")
    print("  2. scripts\\start_server.bat")
    print("  3. conda activate videorag && python main.py")
    print("  端口冲突: netstat -ano | findstr \":8001 :8002\"  →  taskkill /F /PID <pid>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
