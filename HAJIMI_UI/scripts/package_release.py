"""Create HAJIMI full release zip — defense/demo comprehensive package.

Strategy: walk ALL top-level items in repo root, exclude only what must not ship.
This ensures C-end, web-admin, Vosk model etc. are all included.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Directories to skip entirely (not walked) ──
EXCLUDE_DIR_NAMES = {
    ".venv",               # Python virtual environments (3 places), pip install
    "__pycache__",          # Compiled bytecode cache
    ".pytest_cache",        # Test runner cache
    ".git",                 # Version control history
    "node_modules",          # Frontend dependencies, npm install
    "OmniParser",           # Heavy GPU/conda dependency, not in source bundle
    ".cursor",              # Cursor IDE internals
    "mcps",                 # MCP server descriptors
    "agent-transcripts",    # Historical chat transcripts
    "dist",                 # Previous zip outputs, avoid nesting
    "new_JIMI",             # Deprecated alternate branch
    "项目文档",              # Defense PPT + design docs, delivered separately
    "工作进度",              # Internal daily progress logs
    "参考文档",              # Non-canonical reference docs
    "server",               # Root legacy server (replaced by server_A + HAJIMI_UI/server)
    "terminals",            # IDE terminal session logs
}

# ── File-level patterns to drop ──
EXCLUDE_FILE_GLOBS = (
    "*.pyc",
    "*.pyo",
    ".env",
    "hajimi.db-shm",
    "hajimi.db-wal",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "~$*",
)


def _should_skip(path: Path) -> bool:
    """Return True if this file or directory should be excluded from the zip."""
    parts = path.parts
    if any(part in EXCLUDE_DIR_NAMES for part in parts):
        return True
    name = path.name
    for pattern in EXCLUDE_FILE_GLOBS:
        if fnmatch.fnmatch(name, pattern):
            # .env.example is a template — keep it
            if name == ".env.example":
                return False
            return True
    return False


def _iter_files() -> list[tuple[Path, str]]:
    """Walk repo root; return (absolute_path, relative_arcname) sorted."""
    out: list[tuple[Path, str]] = []
    for entry in sorted(REPO_ROOT.iterdir(), key=lambda e: e.name.lower()):
        name = entry.name
        if name in EXCLUDE_DIR_NAMES:
            continue
        if _should_skip(entry):
            continue
        if entry.is_file():
            out.append((entry, name.replace("\\", "/")))
            continue
        if not entry.is_dir():
            continue
        for root, dirnames, filenames in os.walk(str(entry)):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES]
            root_path = Path(root)
            for fname in sorted(filenames, key=str.lower):
                file_path = root_path / fname
                if _should_skip(file_path):
                    continue
                rel = str(file_path.relative_to(REPO_ROOT)).replace("\\", "/")
                out.append((file_path, rel))
    return sorted(out, key=lambda x: x[1].lower())


def _verify_package(files: list[tuple[Path, str]]) -> int:
    """Check that key components are present; return 0 if ok, 1 if missing."""
    arcs = {arc for _, arc in files}

    required = {
        "HAJIMI_UI/main.py": "B-end entry",
        "client/voice_setup.py": "C-end voice verification",
        "安装全栈.bat": "Full stack install script",
        "启动全栈.bat": "Full stack launch script",
        "打包说明.md": "Recipient README",
    }
    required_l5 = {
        "server_A/scripts/start_server.bat": "L5 Sidecar launcher (L5 auto-execute unavailable)",
    }

    exit_code = 0
    for path, label in required.items():
        if path not in arcs:
            print(f"[package] MISSING required: {label} ({path})")
            exit_code = 1

    for path, label in required_l5.items():
        if path not in arcs:
            print(f"[package] MISSING: {label}{' ' * (len(label) - 50)} ({path})")

    # Probes by prefix
    checks = [
        ("client/", "C-end voice/audit module"),
        ("web-admin/", "Admin dashboard"),
        ("models/vosk-model-small-cn-0.22/", "Vosk Chinese ASR model"),
        ("launchers/", "Launcher shortcuts"),
    ]
    for prefix, label in checks:
        if not any(a.startswith(prefix) for a in arcs):
            print(f"[package] MISSING: {label} ({prefix}...)")
            exit_code = 1

    # Security: verify .env files are excluded
    env_leaks = [a for a in arcs if a.endswith("/.env") and not a.endswith(".example")]
    if env_leaks:
        print(f"[package] SECURITY: .env files leaked! {env_leaks}")
        exit_code = 1

    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Package HAJIMI full release zip")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output zip path (default: dist/HAJIMI-release-YYYYMMDD.zip)",
    )
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d")
    out_path = args.output or (REPO_ROOT / "dist" / f"HAJIMI-release-{stamp}.zip")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = _iter_files()
    print(f"[package] Found {len(files)} files to archive")

    verify_code = _verify_package(files)

    print(f"[package] Writing {out_path} ...")
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, (file_path, arcname) in enumerate(files, start=1):
            if i % 500 == 0 or i == 1:
                print(f"[package]   ... {i}/{len(files)} files")
            zf.write(file_path, arcname)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"[package] Wrote {out_path} ({len(files)} files, {size_mb:.1f} MB)")

    if verify_code:
        print("[package] WARN: some components missing or security leak — review above")
    else:
        print("[package] All checks passed")

    print("[package] Recipient: unzip -> 安装全栈.bat -> edit server/.env -> 启动全栈.bat")
    return verify_code


if __name__ == "__main__":
    raise SystemExit(main())
