"""
MemoryDeduper — 记忆去重合并，更新覆盖策略。

同 user_id + 同 category 的记忆，相似度 >0.85 时新覆盖旧。
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from server.database.repository import MemoryRepository
from server.services.memory.embedder import cosine_similarity, encode, from_blob

logger = logging.getLogger(__name__)

MERGE_THRESHOLD = 0.85


def check_and_merge(
    user_id: str,
    summary: str,
    category: Optional[str],
    memory_type: str,
    trigger_query: str,
    embedding: Optional[np.ndarray],
) -> Optional[str]:
    """Check if a similar active memory already exists for this user+category.

    If cosine_similarity > MERGE_THRESHOLD: deactivate old, insert new (update-cover).
    Otherwise: insert as new independent memory.

    Returns:
        memory_id of the created memory, or None on unexpected error.
    """
    if embedding is None:
        logger.warning("Embedding is None — skipping memory insert")
        return None

    if category is None:
        # No category — no dedup, just insert
        return _insert(user_id, memory_type, trigger_query, summary, embedding, category)

    # Get all active memories for this user with same category
    existing = MemoryRepository.get_active_by_user(user_id)
    same_category = [m for m in existing if m.category == category and m.embedding is not None]

    for old in same_category:
        try:
            old_vec = from_blob(old.embedding)
            sim = cosine_similarity(embedding, old_vec)
            if sim > MERGE_THRESHOLD:
                logger.info(
                    "Dedup merge: new='%s' covers old='%s' (sim=%.3f, category=%s)",
                    summary[:50],
                    old.summary[:50],
                    sim,
                    category,
                )
                # Deactivate old
                MemoryRepository.deactivate(old.memory_id)
                # Insert new (covers old)
                return _insert(user_id, memory_type, trigger_query, summary, embedding, category)
        except Exception as e:
            logger.warning("Dedup comparison failed for memory %s: %s", old.memory_id, e)
            continue

    # No similar memory found — insert as new
    return _insert(user_id, memory_type, trigger_query, summary, embedding, category)


def _insert(
    user_id: str,
    memory_type: str,
    trigger_query: str,
    summary: str,
    embedding: np.ndarray,
    category: Optional[str],
) -> Optional[str]:
    """Insert a memory row into DB. Truncates summary to 500 chars.

    Returns memory_id on success, None on failure.
    """
    truncated = summary[:500]
    blob = embedding.astype(np.float32).tobytes()
    try:
        mem = MemoryRepository.create(
            user_id=user_id,
            memory_type=memory_type,
            trigger_query=trigger_query,
            summary=truncated,
            embedding_bytes=blob,
            category=category,
        )
        return mem.memory_id
    except Exception as e:
        logger.error("Failed to insert memory: %s", e)
        return None
