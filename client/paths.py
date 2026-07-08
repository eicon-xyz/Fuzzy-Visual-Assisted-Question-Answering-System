"""C 端运行时路径（审计库等与 cwd 无关的用户数据目录）。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def hajimi_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = Path(base) / "HAJIMI"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def default_audit_db_path() -> str:
    return str(hajimi_data_dir() / "audit_queue.db")


def _legacy_audit_db_candidates() -> list[Path]:
    cwd = Path.cwd()
    roots = {cwd, cwd.parent}
    candidates: list[Path] = []
    for base in roots:
        candidates.append(base / "client" / "audit" / "audit_queue.db")
        candidates.append(base / "HAJIMI_UI" / "client" / "audit" / "audit_queue.db")
    seen: set[Path] = set()
    out: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def migrate_legacy_audit_db(target: str | None = None) -> None:
    """若新路径无库，从旧 cwd 相对路径复制（一次性）。"""
    target_path = Path(target or default_audit_db_path())
    if target_path.is_file():
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    for legacy in _legacy_audit_db_candidates():
        if legacy.is_file() and legacy.resolve() != target_path.resolve():
            shutil.copy2(legacy, target_path)
            return
