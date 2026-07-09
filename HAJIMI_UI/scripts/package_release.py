"""Create HAJIMI L4+L5 source release zip (scheme 1)."""
from __future__ import annotations

import argparse
import fnmatch
import os
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

INCLUDE_TOP = (
    "HAJIMI_UI",
    "server_A",
    "安装全栈.bat",
    "启动全栈.bat",
    "验收.bat",
    "打包.bat",
    "打包说明.md",
    "启动指南.md",
)

EXCLUDE_DIR_NAMES = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".git",
    "node_modules",
    "OmniParser",
    ".cursor",
    "mcps",
}

EXCLUDE_FILE_GLOBS = (
    "*.pyc",
    "*.pyo",
    ".env",
    "hajimi.db-shm",
    "hajimi.db-wal",
    ".DS_Store",
)

EXCLUDE_PATH_PARTS = (
    "/server/.env",
    "\\server\\.env",
    "/.env",
)


def _should_skip(path: Path, rel: str) -> bool:
    parts = path.parts
    if any(part in EXCLUDE_DIR_NAMES for part in parts):
        return True
    name = path.name
    for pattern in EXCLUDE_FILE_GLOBS:
        if fnmatch.fnmatch(name, pattern):
            return True
    for marker in EXCLUDE_PATH_PARTS:
        if marker in rel.replace("/", os.sep):
            if name == ".env":
                return True
    return False


def _iter_files() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for top in INCLUDE_TOP:
        src = REPO_ROOT / top
        if not src.exists():
            continue
        if src.is_file():
            out.append((src, top.replace("\\", "/")))
            continue
        for root, dirnames, filenames in os.walk(src):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES]
            root_path = Path(root)
            for name in filenames:
                file_path = root_path / name
                rel = str(file_path.relative_to(REPO_ROOT)).replace("\\", "/")
                if _should_skip(file_path, rel):
                    continue
                out.append((file_path, rel))
    return sorted(out, key=lambda x: x[1].lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="Package HAJIMI L4+L5 release zip")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output zip path (default: dist/HAJIMI-release-YYYYMMDD.zip)",
    )
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d")
    out_path = args.output or (REPO_ROOT / "dist" / f"HAJIMI-release-{stamp}.zip")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = _iter_files()
    if not any("HAJIMI_UI/" in arc for _, arc in files):
        print("[package] ERROR: HAJIMI_UI not found in file list")
        return 1
    if not any("server_A/" in arc for _, arc in files):
        print("[package] ERROR: server_A not found — L5 will not work in release")
        return 1

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path, arcname in files:
            zf.write(file_path, arcname)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"[package] Wrote {out_path} ({len(files)} files, {size_mb:.1f} MB)")
    print("[package] Recipient: unzip -> 安装全栈.bat -> edit server/.env -> 启动全栈.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
