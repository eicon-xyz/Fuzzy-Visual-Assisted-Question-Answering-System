"""
HAJIMI 自动记忆系统 — 全自动用户习惯学习

三层记忆：用户画像 (profile) / 成功模式 (success_pattern) / 失败指纹 (failure_lesson)
"""

from server.services.memory.embedder import encode, from_blob, to_blob

try:
    from server.services.memory.extractor import MemoryExtractor
    from server.services.memory.retriever import MemoryRetriever
except ImportError:
    # extractor/retriever will be available once created in subsequent tasks
    MemoryExtractor = None  # type: ignore
    MemoryRetriever = None  # type: ignore

__all__ = [
    "MemoryExtractor",
    "MemoryRetriever",
    "encode",
    "to_blob",
    "from_blob",
]
