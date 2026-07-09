"""Release install helper: create .env files and sync L5 Sidecar from canonical 8010."""
from __future__ import annotations

import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.defaults import DEFAULT_DEMO_KEY, DEFAULT_L5_PORT  # noqa: E402
from core.env_sync import (  # noqa: E402
    ENV_PATH,
    EXAMPLE_PATH,
    resolve_l5_env_path,
    sync_l5_sidecar_env,
    sync_server_env,
)
from core.user_settings import DEFAULT_SETTINGS  # noqa: E402


def _ensure_canonical_env() -> None:
    if ENV_PATH.is_file():
        return
    if not EXAMPLE_PATH.is_file():
        raise FileNotFoundError(f"Missing {EXAMPLE_PATH}")
    ENV_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[release] created {ENV_PATH} from example")


def _ensure_l5_env_from_canonical() -> None:
    l5_path = resolve_l5_env_path()
    if l5_path is None:
        raise FileNotFoundError(
            "L5 Sidecar not found — ensure server_A/ sits next to HAJIMI_UI/"
        )
    if l5_path.is_file():
        return

    text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.is_file() else ""
    if not text.strip() and EXAMPLE_PATH.is_file():
        text = EXAMPLE_PATH.read_text(encoding="utf-8")

    lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^HAJIMI_PORT=", line.strip()):
            lines.append(f"HAJIMI_PORT={DEFAULT_L5_PORT}")
            continue
        if re.match(r"^HAJIMI_HOST=", line.strip()):
            lines.append("HAJIMI_HOST=127.0.0.1")
            continue
        lines.append(line)

    l5_path.parent.mkdir(parents=True, exist_ok=True)
    l5_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"[release] created {l5_path} from canonical 8010 template (port {DEFAULT_L5_PORT})")


def main() -> int:
    _ensure_canonical_env()
    _ensure_l5_env_from_canonical()

    settings = deepcopy(DEFAULT_SETTINGS)
    settings["demo_key"] = DEFAULT_DEMO_KEY
    sync_server_env(settings)
    sync_l5_sidecar_env(settings)

    print("[release] env bootstrap complete")
    print("[release] IMPORTANT: edit HAJIMI_UI\\server\\.env and set LLM_API_KEY before first run")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as exc:
        print(f"[release] ERROR: {exc}")
        raise SystemExit(1) from exc
