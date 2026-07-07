"""仓库路径解析（供 B 端加载根项目 client/ 模块）。"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_hajimi_ui_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_repo_root() -> Path:
    env = (os.environ.get("HAJIMI_REPO_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    return resolve_hajimi_ui_root().parent
