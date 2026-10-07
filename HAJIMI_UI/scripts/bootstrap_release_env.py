"""Release install helper: 创建 L5 Sidecar server/.env（模板 + :8011 固定项）。

L4/旧 A 端已删除：唯一需要引导的 .env 是 server_A/server/.env。
"""
from __future__ import annotations

import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.defaults import DEFAULT_L5_PORT  # noqa: E402
from core.env_sync import (  # noqa: E402
    resolve_l5_env_path,
    sync_l5_sidecar_env,
)
from core.user_settings import DEFAULT_SETTINGS  # noqa: E402


def _ensure_l5_env() -> Path:
    l5_path = resolve_l5_env_path()
    if l5_path is None:
        raise FileNotFoundError(
            "L5 Sidecar not found — ensure server_A/ sits next to HAJIMI_UI/"
        )
    example = l5_path.parent / ".env.example"
    if l5_path.is_file():
        text = l5_path.read_text(encoding="utf-8")
    elif example.is_file():
        text = example.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"Missing {example}")

    lines: list[str] = []
    port_set = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^HAJIMI_PORT=", stripped):
            lines.append(f"HAJIMI_PORT={DEFAULT_L5_PORT}")
            port_set = True
            continue
        if re.match(r"^OMNIPARSER_ENABLED=", stripped):
            lines.append("OMNIPARSER_ENABLED=false")
            continue
        lines.append(line)
    if not port_set:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"HAJIMI_PORT={DEFAULT_L5_PORT}")
    if not any(re.match(r"^OMNIPARSER_ENABLED=", x.strip()) for x in lines):
        lines.append("OMNIPARSER_ENABLED=false")

    l5_path.parent.mkdir(parents=True, exist_ok=True)
    l5_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"[release] ensured {l5_path} (port {DEFAULT_L5_PORT}, OMNIPARSER_ENABLED=false)")
    return l5_path


def main() -> int:
    _ensure_l5_env()

    settings = deepcopy(DEFAULT_SETTINGS)
    sync_l5_sidecar_env(settings)

    print("[release] env bootstrap complete")
    print("[release] IMPORTANT: edit server_A\\server\\.env and set DEEPSEEK_API_KEY / LLM_API_KEY before first run")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as exc:
        print(f"[release] ERROR: {exc}")
        raise SystemExit(1) from exc
