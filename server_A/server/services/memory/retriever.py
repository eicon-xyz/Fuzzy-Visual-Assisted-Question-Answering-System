"""
MemoryRetriever — 检索相关记忆，注入 Planner/Executor Prompt。

内存缓存 + 线程安全 + Token 预算控制。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from server.database.repository import MemoryRepository
from server.services.memory.embedder import cosine_similarity, encode, from_blob

logger = logging.getLogger(__name__)

# Token budget
MAX_TOKEN_BUDGET = 300
COMPLEX_SCREEN_TOKEN_BUDGET = 150
COMPLEX_SCREEN_ELEMENT_THRESHOLD = 50
TOKEN_PER_CHINESE_CHAR = 1.0
TOKEN_PER_ENGLISH_WORD = 0.75


@dataclass
class MemoryCacheEntry:
    """In-memory cache entry for fast retrieval."""
    memory_id: str
    user_id: str
    memory_type: str
    category: Optional[str]
    trigger_query: str
    summary: str
    embedding: np.ndarray


class MemoryRetriever:
    """Thread-safe retriever with in-memory embedding cache."""

    def __init__(self):
        self._memory_cache: Dict[str, List[MemoryCacheEntry]] = {}
        self._cache_lock = threading.Lock()

    # ── Cache management ──────────────────────────────────────────────

    def load_cache(self) -> None:
        """Load all active memories from DB into memory cache at startup."""
        from server.database import SessionLocal

        db = SessionLocal()
        try:
            from server.database.models import Memory

            rows = db.query(Memory).filter(Memory.is_active == True).all()
            loaded = 0
            with self._cache_lock:
                for row in rows:
                    if row.embedding is None:
                        continue
                    try:
                        vec = from_blob(row.embedding)
                    except Exception:
                        continue
                    entry = MemoryCacheEntry(
                        memory_id=row.memory_id,
                        user_id=row.user_id,
                        memory_type=row.memory_type,
                        category=row.category,
                        trigger_query=row.trigger_query,
                        summary=row.summary,
                        embedding=vec,
                    )
                    self._memory_cache.setdefault(row.user_id, []).append(entry)
                    loaded += 1
            logger.info("MemoryRetriever cache loaded: %d entries across %d users",
                        loaded, len(self._memory_cache))
        finally:
            db.close()

    def _update_cache(
        self,
        user_id: str,
        memory_id: str,
        memory_type: str,
        category: Optional[str],
        trigger_query: str,
        summary: str,
        embedding: np.ndarray,
    ) -> None:
        """Thread-safe cache update after a new memory is persisted."""
        entry = MemoryCacheEntry(
            memory_id=memory_id,
            user_id=user_id,
            memory_type=memory_type,
            category=category,
            trigger_query=trigger_query,
            summary=summary,
            embedding=embedding,
        )
        with self._cache_lock:
            user_entries = self._memory_cache.setdefault(user_id, [])
            # Replace if same memory_id exists (shouldn't happen for new, but safe)
            for i, e in enumerate(user_entries):
                if e.memory_id == memory_id:
                    user_entries[i] = entry
                    return
            user_entries.append(entry)

    def add_to_cache(
        self,
        user_id: str,
        memory_id: str,
        memory_type: str,
        category: Optional[str],
        trigger_query: str,
        summary: str,
        embedding: np.ndarray,
    ) -> None:
        """Public API for cache sync after extraction."""
        self._update_cache(user_id, memory_id, memory_type, category, trigger_query, summary, embedding)

    def remove_from_cache(self, user_id: str, memory_id: str) -> None:
        """Public API for cache removal after deactivation."""
        self._remove_from_cache(user_id, memory_id)

    def _remove_from_cache(self, user_id: str, memory_id: str) -> None:
        """Thread-safe removal of a deactivated memory from cache."""
        with self._cache_lock:
            entries = self._memory_cache.get(user_id, [])
            self._memory_cache[user_id] = [
                e for e in entries if e.memory_id != memory_id
            ]

    # ── Retrieval ─────────────────────────────────────────────────────

    def retrieve(
        self,
        user_id: str,
        query: str,
        element_count: Optional[int] = None,
    ) -> str:
        """Retrieve relevant memories and format for prompt injection.

        Args:
            user_id: Current user ID for multi-user isolation.
            query: User's raw natural language input (used for embedding match).
            element_count: Current screen OmniParser element count.
                           If >50, budget downgrades to 150 tokens.

        Returns:
            Formatted memory string for prompt injection, or empty string.
        """
        with self._cache_lock:
            entries = list(self._memory_cache.get(user_id, []))

        if not entries:
            return ""

        # Encode query
        query_vec = encode(query)
        if query_vec is None:
            # Embedding model unavailable — fall back to recent memories
            logger.info("Embedding model unavailable, using fallback retrieval (recent first)")
            recent = entries[-2:] if len(entries) >= 2 else entries
            budget = MAX_TOKEN_BUDGET if element_count is None or element_count <= COMPLEX_SCREEN_ELEMENT_THRESHOLD else COMPLEX_SCREEN_TOKEN_BUDGET
            return self._format_result(recent, budget)

        # Compute similarity for all cached entries
        scored = []
        for entry in entries:
            sim = cosine_similarity(query_vec, entry.embedding)
            scored.append((sim, entry))

        # Sort descending, take top-5
        scored.sort(key=lambda x: x[0], reverse=True)
        top5 = scored[:5]

        # Filter: prefer success_pattern, then profile, then failure_lesson
        # Exclude resolved/irrelevant failure lessons
        filtered = [(s, e) for s, e in top5 if e.memory_type != "failure_lesson"]
        # Add failure_lesson only if active
        failures = [(s, e) for s, e in top5 if e.memory_type == "failure_lesson"]
        filtered.extend(failures)
        filtered.sort(key=lambda x: x[0], reverse=True)

        # Keep top-2
        top2 = filtered[:2]
        if not top2:
            return ""

        # Token budget
        is_complex = element_count is not None and element_count > COMPLEX_SCREEN_ELEMENT_THRESHOLD
        budget = COMPLEX_SCREEN_TOKEN_BUDGET if is_complex else MAX_TOKEN_BUDGET

        # Take only top-1 if complex screen
        if is_complex:
            top2 = top2[:1]

        return self._format_result([e for _, e in top2], budget)

    # ── Formatting ──────────────────────────────────────────────────────

    def _format_result(self, entries: List[MemoryCacheEntry], budget: int) -> str:
        """Format memory entries into prompt-injection string, respecting token budget."""
        lines = ["[相关记忆]"]
        tokens_used = 0
        for i, entry in enumerate(entries, 1):
            line = f"{i}. {entry.summary}"
            est_tokens = _estimate_tokens(line)
            if tokens_used + est_tokens > budget:
                # Truncate to fit
                remaining = budget - tokens_used
                if remaining > 20:  # Need at least some meaningful content
                    truncated = _truncate_to_tokens(line, remaining)
                    lines.append(truncated)
                break
            lines.append(line)
            tokens_used += est_tokens

        return "\n".join(lines)


# ── Token estimation helpers ─────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """Rough token estimation: Chinese chars ≈1 token, English words ≈0.75 token."""
    import re

    # Count Chinese characters
    chinese = len(re.findall(r'[一-鿿]', text))
    # Count English word-like sequences
    english = len(re.findall(r'[a-zA-Z0-9]+', text))
    # Punctuation and whitespace ≈1 token per 4 chars
    other = len(re.findall(r'[^一-鿿a-zA-Z0-9]', text))
    return int(chinese * TOKEN_PER_CHINESE_CHAR + english * TOKEN_PER_ENGLISH_WORD + other * 0.25)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within token budget, appending '…'."""
    result = ""
    tokens = 0
    for char in text:
        if char == '\n':
            continue
        est = 1.0 if '一' <= char <= '鿿' else 0.75 if char.isalnum() else 0.25
        if tokens + est > max_tokens - 1:  # Reserve 1 token for '…'
            result += "…"
            break
        result += char
        tokens += est
    return result


# ── Global singleton ─────────────────────────────────────────────────

_retriever: Optional[MemoryRetriever] = None


def get_retriever() -> MemoryRetriever:
    """Get or create the global MemoryRetriever singleton."""
    global _retriever
    if _retriever is None:
        _retriever = MemoryRetriever()
    return _retriever
