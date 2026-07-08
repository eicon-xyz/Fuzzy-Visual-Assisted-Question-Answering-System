#!/usr/bin/env python3
"""Structured deploy check: venv / .env / tunnel / A-end / L5 (no service start)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _l5_root() -> Path:
    env = os.environ.get("HAJIMI_L5_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return (ROOT.parent / "new_JIMI" / "HAJIMI_UI").resolve()


def _venv_import_ok(venv_py: Path) -> tuple[bool, str]:
    if not venv_py.is_file():
        return False, "venv missing"
    cmd = [
        str(venv_py),
        "-c",
        "import fastapi, uvicorn, sqlalchemy, psutil",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return True, "OK"
        return False, (r.stderr or r.stdout or "import failed").strip()[:120]
    except Exception as exc:
        return False, str(exc)[:120]


def _resolve_ui_python() -> Path | None:
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        return venv_py
    env = os.environ.get("VIDEO_RAG_PY", "").strip()
    if env and Path(env).is_file():
        return Path(env)
    try:
        import shutil

        found = shutil.which("python")
        if found:
            return Path(found)
    except Exception:
        pass
    return Path(sys.executable)


def _ui_ok() -> tuple[bool, str]:
    ui_py = _resolve_ui_python()
    if ui_py is None:
        return False, "python not found"
    r = subprocess.run(
        [str(ui_py), str(SCRIPTS / "check_ui_env.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode == 0:
        return True, f"OK ({ui_py.name})"
    return False, "missing PyQt5/mss — run scripts\\setup.bat"


def _http_json(url: str, timeout: float = 3.0) -> tuple[bool, str, dict | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return False, f"HTTP {resp.status}", None
            data = json.loads(resp.read().decode("utf-8"))
            return True, "OK", data if isinstance(data, dict) else None
    except urllib.error.HTTPError as exc:
        if exc.code in (503,):
            try:
                data = json.loads(exc.read().decode("utf-8"))
                return True, f"HTTP {exc.code} degraded", data if isinstance(data, dict) else None
            except Exception:
                return False, f"HTTP {exc.code}", None
        return False, f"HTTP {exc.code}", None
    except Exception as exc:
        reason = getattr(exc, "reason", exc)
        return False, str(reason)[:120], None


def _l5_live(port: int = 8011) -> tuple[bool, str]:
    base = f"http://127.0.0.1:{port}"
    for path in ("/api/demo/health/live", "/api/demo/health"):
        ok, detail, _ = _http_json(base + path, timeout=3.0)
        if ok:
            return True, detail
    return False, "not listening"


def main() -> int:
    rows: list[tuple[str, bool, str]] = []
    env_fail = False
    link_fail = False

    venv8010 = ROOT / "server" / ".venv" / "Scripts" / "python.exe"
    ok, detail = _venv_import_ok(venv8010)
    rows.append(("8010 A-end venv", ok, detail))
    if not ok:
        env_fail = True

    l5 = _l5_root()
    venv8011 = l5 / "server" / ".venv" / "Scripts" / "python.exe"
    ok, detail = _venv_import_ok(venv8011)
    rows.append(("8011 L5 venv", ok, detail if ok else f"{detail} @ {l5}"))
    if not ok:
        env_fail = True

    ok, detail = _ui_ok()
    rows.append(("B-end UI deps", ok, detail))
    if not ok:
        env_fail = True

    env8010 = ROOT / "server" / ".env"
    rows.append(("8010 server/.env", env8010.is_file(), str(env8010) if env8010.is_file() else "missing — copy .env.example"))

    env8011 = l5 / "server" / ".env"
    rows.append(("8011 L5 server/.env", env8011.is_file(), str(env8011) if env8011.is_file() else "missing — copy .env.example"))

    try:
        sys.path.insert(0, str(SCRIPTS))
        from check_gpu_api_tunnel import check as tunnel_check

        ok, detail = tunnel_check()
        rows.append((":9800 GPU tunnel", ok, str(detail)[:120] if not ok else "ready"))
        if not ok:
            link_fail = True
    except Exception as exc:
        rows.append((":9800 GPU tunnel", False, str(exc)[:120]))
        link_fail = True

    port = int(os.environ.get("HAJIMI_PORT", "8010"))
    ok, detail, health = _http_json(f"http://127.0.0.1:{port}/api/demo/health", timeout=3.0)
    if ok and health:
        omni = health.get("omniparser_ready")
        extra = f"omniparser_ready={omni}"
        if omni is False:
            link_fail = True
            ok = False
        rows.append((":8010 A-end health", ok, extra))
    else:
        rows.append((":8010 A-end health", False, detail))
        link_fail = True

    ok, detail = _l5_live(int(os.environ.get("L5_API_PORT", "8011")))
    rows.append((":8011 L5 Sidecar", ok, detail))
    if not ok:
        link_fail = True

    print("=" * 60)
    print(" HAJIMI deploy check (read-only, no GPU remote start)")
    print("=" * 60)
    for name, passed, info in rows:
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {name}: {info}")
    print("=" * 60)

    if env_fail:
        print("[check_deploy] Environment not ready — run 启动HAJIMI.bat or scripts\\ensure_hajimi_gpu_prereqs.bat")
        return 1
    if link_fail:
        print("[check_deploy] Environment OK; backend links not ready (exit 2).")
        print("  Fix: connect campus network and run 启动HAJIMI.bat, or start tunnel manually.")
        return 2
    print("[check_deploy] All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
