"""B 端：热点/局域网联调 — 写内网 API 设置 + health 预检（直连远程 8010）。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_HOST = "192.168.137.1"
DEFAULT_PORT = 8010
DEFAULT_DEMO_KEY = "hajimi-demo-2026"
LAN_BASE_FILE = Path(os.environ.get("TEMP", ".")) / "hajimi_lan_base.txt"


def _fetch_health(base: str, timeout: float = 8.0) -> dict:
    url = f"{base.rstrip('/')}/api/demo/health"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _resolve_host(args: argparse.Namespace) -> str:
    if args.host is not None:
        return args.host.strip()
    if args.no_prompt:
        return DEFAULT_HOST
    try:
        raw = input(f"后端 IP [{DEFAULT_HOST}]: ").strip()
    except EOFError:
        raw = ""
    return raw or DEFAULT_HOST


def _build_base(host: str, port: int) -> str:
    host = host.strip()
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"http://{host}:{port}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="配置 B 端内网 API（热点联调，远程统一 8010 + L5）",
    )
    parser.add_argument(
        "--host",
        default=None,
        help=f"后端 IPv4 或完整 URL（默认交互，回车={DEFAULT_HOST}）",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="A 端端口")
    parser.add_argument("--demo-key", default=DEFAULT_DEMO_KEY, help="X-Demo-Key")
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="不交互，直接使用默认 IP",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="仅 health 预检，不写设置",
    )
    args = parser.parse_args()

    host = _resolve_host(args)
    base = _build_base(host, args.port)
    print(f"[LAN] 目标 A 端: {base}")

    try:
        health = _fetch_health(base)
    except urllib.error.HTTPError as exc:
        print(f"[LAN] FAIL: HTTP {exc.code} — {base}/api/demo/health")
        return 1
    except Exception as exc:
        print(f"[LAN] FAIL: 无法连接 {base} — {exc}")
        print("  请确认：已连热点、队友 8010 已启动且 HAJIMI_HOST=0.0.0.0、防火墙已放行")
        return 1

    status = health.get("status", "?")
    omni = health.get("omniparser_ready")
    backend = health.get("detector_backend", "?")
    print(f"[LAN] health OK — status={status!r} omniparser_ready={omni!r} detector_backend={backend!r}")

    if omni is False:
        print(
            "[LAN] WARN: 远程 A 端 OmniParser 未就绪 — 请确认队友 A 端已连远程 OP"
            "（OMNIPARSER_URL 指向 GPU :9800 或等效地址）。"
        )
        print("      将继续启动 B 端 UI；视觉相关功能可能不可用直至 OP 就绪。")

    LAN_BASE_FILE.write_text(base + "\n", encoding="utf-8")
    print(f"HAJIMI_LAN_BASE={base}")

    if args.check_only:
        return 0

    from core.user_settings import _settings_path, save_settings_fragment

    merged = save_settings_fragment(
        {
            "deployment_mode": "intranet",
            "a_end_url": base,
            "demo_key": args.demo_key,
            "routing_mode": "l5",
        }
    )
    print(f"[LAN] 已写入 {_settings_path()}")
    print(f"      deployment_mode=intranet  routing_mode=l5")
    print(f"      a_end_url={merged.get('a_end_url')}")

    from core.user_settings import apply_user_settings

    apply_user_settings(merged)
    print("[LAN] 环境变量已刷新（L5_API_URL 将与 a_end_url 同址）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
