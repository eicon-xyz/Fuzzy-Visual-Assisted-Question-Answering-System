"""T6 memory 模块单元测试——测缓存管理/检索容错（不依赖 DB/LLM/embedding 真件）。"""
from __future__ import annotations

import numpy as np
import pytest

from server.services.memory.retriever import MemoryCacheEntry, MemoryRetriever


def _emb(n=4):
    return np.array([float(i) for i in range(n)], dtype="float32")


def _add(r, uid, mid, query, summary, emb=None):
    r.add_to_cache(uid, mid, "lesson", None, query, summary, emb if emb is not None else _emb())


def test_cache_add_and_isolation():
    r = MemoryRetriever()
    _add(r, "u1", "m1", "打开记事本", "用 notepad.exe")
    _add(r, "u2", "m2", "计算器", "用 calc.exe")
    assert len(r._memory_cache["u1"]) == 1
    assert len(r._memory_cache["u2"]) == 1
    assert r._memory_cache["u1"][0].memory_id == "m1"


def test_cache_replace_same_id():
    r = MemoryRetriever()
    _add(r, "u1", "m1", "旧", "old")
    _add(r, "u1", "m1", "新", "new")
    assert len(r._memory_cache["u1"]) == 1
    assert r._memory_cache["u1"][0].summary == "new"


def test_cache_remove():
    r = MemoryRetriever()
    _add(r, "u1", "m1", "a", "x")
    _add(r, "u1", "m2", "b", "y")
    r.remove_from_cache("u1", "m1")
    assert [e.memory_id for e in r._memory_cache["u1"]] == ["m2"]
    # 删不存在的 id 不炸
    r.remove_from_cache("u1", "nope")
    r.remove_from_cache("u9", "nope")


def test_retrieve_empty_returns_empty_string():
    r = MemoryRetriever()
    assert r.retrieve("u1", "anything") == ""


def test_retrieve_embedding_unavailable_fallback(monkeypatch):
    """encode 返回 None（embedding 模型不可用）→ 回退最近记忆且不抛异常。"""
    import server.services.memory.retriever as rt

    monkeypatch.setattr(rt, "encode", lambda q: None)
    r = MemoryRetriever()
    _add(r, "u1", "m1", "q1", "第一条记忆", emb=_emb())
    _add(r, "u1", "m2", "q2", "第二条记忆", emb=_emb())
    out = r.retrieve("u1", "任意查询")
    assert isinstance(out, str) and "第二条记忆" in out  # 最近优先


def test_retrieve_formats_without_embedding_entries():
    r = MemoryRetriever()
    _add(r, "u1", "m1", "打开记事本", "用 notepad.exe 打开", emb=_emb())
    out = r.retrieve("u1", "打开记事本")
    assert "[相关记忆]" in out
    assert "notepad.exe" in out


def test_memory_cache_entry_roundtrip():
    e = MemoryCacheEntry(memory_id="m1", user_id="u", memory_type="lesson",
                         category=None, trigger_query="q", summary="s",
                         embedding=_emb())
    assert e.memory_id == "m1" and e.summary == "s"
    assert e.embedding.shape == (4,)
