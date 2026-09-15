"""写 L5 自动执行模式部署配置（用户设置 + Sidecar .env 固定项）。

L4 指引模式（旧 A 端 :8010 / OmniParser / routing 选项）已删除：
  - Sidecar server/.env 写 OMNIPARSER_ENABLED=false、ROUTING_MODE=l5、
    HAJIMI_HOST=127.0.0.1 / HAJIMI_PORT=8011（防任何组件再探测 :9800/:8002）
  - user_settings 的模型 key 经 env_sync.sync_l5_sidecar_env 同步
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.defaults import DEFAULT_DEMO_KEY  # noqa: E402
from core.env_sync import (  # noqa: E402
    _upsert_env_lines,
    resolve_l5_env_path,
    sync_l5_sidecar_env,
)
from core.user_settings import apply_user_settings, save_settings_fragment  # noqa: E402

_FIXED_L5_ENV = {
    "HAJIMI_HOST": "127.0.0.1",
    "HAJIMI_PORT": "8011",
    "OMNIPARSER_ENABLED": "false",
    "ROUTING_MODE": "l5",
}


def _write_fixed_l5_env() -> Path | None:
    env_path = resolve_l5_env_path()
    if env_path is None:
        return None
    example = env_path.parent / ".env.example"
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
    elif example.is_file():
        text = example.read_text(encoding="utf-8")
    else:
        text = ""
    updates = dict(_FIXED_L5_ENV)
    updates["HAJIMI_DEMO_KEY"] = os.environ.get("HAJIMI_DEMO_KEY") or DEFAULT_DEMO_KEY
    merged = _upsert_env_lines(text.splitlines(), updates)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")
    return env_path


def main() -> int:
    merged = save_settings_fragment({})
    apply_user_settings(merged)

    path = _write_fixed_l5_env()
    if path is None:
        print("[l5] ERROR: L5 Sidecar (server_A) not found — 请确认仓库含 server_A/ 或设置 HAJIMI_L5_ROOT")
        return 1
    print(f"[l5] fixed Sidecar env -> {path} (OMNIPARSER_ENABLED=false ROUTING_MODE=l5 :8011)")

    try:
        synced = sync_l5_sidecar_env(merged)
        if synced:
            print(f"[l5] synced model keys -> {synced}")
    except Exception as exc:  # pragma: no cover
        print(f"[l5] WARN env sync failed: {exc}")

    from core.user_settings import _settings_path

    print(f"[l5] settings -> {_settings_path()}")
    print("[l5] mode=auto-execute only (L5 Sidecar :8011, no OmniParser, no :8010)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
