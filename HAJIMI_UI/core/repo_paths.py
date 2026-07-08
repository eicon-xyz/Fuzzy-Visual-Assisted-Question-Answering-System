"""仓库路径解析（供 B 端加载根项目 client/ 模块）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_hajimi_ui_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_repo_root() -> Path:
    env = (os.environ.get("HAJIMI_REPO_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    return resolve_hajimi_ui_root().parent


def ensure_repo_root_on_path() -> Path:
    """将仓库根加入 sys.path 首位，确保 import client 指向根目录 client/。"""
    root = resolve_repo_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def clear_shadow_client_modules() -> None:
    """清除 HAJIMI_UI/client/ 等 namespace 污染后的 client 缓存。"""
    root = resolve_repo_root()
    real_client = root / "client" / "__init__.py"
    if not real_client.is_file():
        return
    mod = sys.modules.get("client")
    if mod is None:
        return
    if getattr(mod, "__file__", None):
        mod_file = Path(mod.__file__).resolve()
        if mod_file == real_client.resolve():
            return
    for key in list(sys.modules):
        if key == "client" or key.startswith("client."):
            del sys.modules[key]
