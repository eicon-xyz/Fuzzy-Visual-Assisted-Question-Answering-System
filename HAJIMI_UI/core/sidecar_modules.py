"""按需加载 server_A Sidecar 中可共享的纯 Python 模块（如红线规则）。

旧 A 端 (HAJIMI_UI/server) 已删除；红线规则的唯一权威实现在
server_A/server/services/redline_service.py（纯 stdlib，无 FastAPI 依赖）。
B 端通过本 helper 以文件路径加载，避免复制规则导致漂移。
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from typing import Optional

_lock = threading.Lock()
_cache: dict[str, object] = {}


def _candidate_paths(rel_path: str) -> list[Path]:
    roots: list[Path] = []
    try:
        from core.paths import resolve_l5_root

        roots.append(resolve_l5_root())
    except Exception:
        pass
    try:
        root = Path(__file__).resolve().parent.parent.parent
        roots += [root / "server_A", root / "server_A" / "server_A"]
    except Exception:
        pass
    seen: set[Path] = set()
    out: list[Path] = []
    for base in roots:
        p = Path(base) / rel_path
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def load_sidecar_module(rel_path: str) -> Optional[object]:
    """加载 Sidecar 纯模块；找不到时返回 None（调用方自行降级）。"""
    name = Path(rel_path).stem
    with _lock:
        cached = _cache.get(name)
        if cached is not None:
            return cached
        for path in _candidate_paths(rel_path):
            if not path.is_file():
                continue
            spec = importlib.util.spec_from_file_location(f"hajimi_sidecar_{name}", path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            _cache[name] = mod
            return mod
    return None


_REDLINE_REL = "server/services/redline_service.py"
_redline_fn: Optional[object] = None
_redline_resolved = False


def get_redline_check():
    """返回 Sidecar 的 check_redline(query)；不可用时返回 None（缓存解析结果）。"""
    global _redline_fn, _redline_resolved
    if not _redline_resolved:
        mod = load_sidecar_module(_REDLINE_REL)
        _redline_fn = getattr(mod, "check_redline", None) if mod else None
        _redline_resolved = True
    return _redline_fn
