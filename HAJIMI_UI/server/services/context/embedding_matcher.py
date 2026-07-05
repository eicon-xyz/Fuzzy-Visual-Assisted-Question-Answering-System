"""
Local embedding-based semantic matching.

Matches OpenGuider's src/context/embedding-matcher.js.
Uses sentence-transformers all-MiniLM-L6-v2 (384-dim) for cosine similarity matching.
"""
from __future__ import annotations
import logging
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_model = None


def _load_model():
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: all-MiniLM-L6-v2...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded.")
        except Exception as e:
            logger.warning(f"Failed to load sentence-transformers: {e}")
            _model = False  # Sentinel to avoid retry
    return _model if _model is not False else None


def get_embedding(text: str) -> Optional[np.ndarray]:
    """Get embedding vector for text. Returns None if model unavailable."""
    model = _load_model()
    if model is None:
        return None
    return model.encode(text, normalize_embeddings=True)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return float(np.dot(a, b))


def find_best_match(
    query: str,
    candidates: List[Tuple[str, object]],
    min_score: float = 0.3,
) -> Optional[Tuple[str, object, float]]:
    """Find the best matching candidate text to the query.

    Args:
        query: The search query / user intent text
        candidates: List of (text, item) tuples to search
        min_score: Minimum cosine similarity to consider a match

    Returns:
        (best_text, best_item, score) or None if no match above threshold
    """
    if not candidates:
        return None

    query_emb = get_embedding(query)
    if query_emb is None:
        return None

    best_score = -1.0
    best_item = None
    best_text = ""

    for text, item in candidates:
        if not text or not text.strip():
            continue
        cand_emb = get_embedding(text)
        if cand_emb is None:
            continue
        score = cosine_similarity(query_emb, cand_emb)
        if score > best_score:
            best_score = score
            best_item = item
            best_text = text

    if best_score >= min_score and best_item is not None:
        return (best_text, best_item, best_score)
    return None


def find_top_matches(
    query: str,
    candidates: List[Tuple[str, object]],
    top_k: int = 3,
    min_score: float = 0.2,
) -> List[Tuple[str, object, float]]:
    """Find top-k matching candidates.

    Returns:
        List of (text, item, score) sorted by score descending
    """
    if not candidates:
        return []

    query_emb = get_embedding(query)
    if query_emb is None:
        return []

    results = []
    for text, item in candidates:
        if not text or not text.strip():
            continue
        cand_emb = get_embedding(text)
        if cand_emb is None:
            continue
        score = cosine_similarity(query_emb, cand_emb)
        if score >= min_score:
            results.append((text, item, score))

    results.sort(key=lambda x: x[2], reverse=True)
    return results[:top_k]
