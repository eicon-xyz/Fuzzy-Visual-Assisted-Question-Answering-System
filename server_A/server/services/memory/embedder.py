"""
Embedding 薄封装 — 复用 embedding_matcher 的编码 + DB blob 读写。
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from server.services.context.embedding_matcher import get_embedding

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2


def encode(text: str) -> Optional[np.ndarray]:
    """Encode text to a 384-dim normalized embedding vector.

    Returns None if the embedding model is unavailable.
    """
    return get_embedding(text)


def to_blob(vec: np.ndarray) -> bytes:
    """Serialize a float32 numpy array to bytes for DB storage."""
    return vec.astype(np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    """Deserialize bytes back to a float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32).reshape(EMBEDDING_DIM)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two (already normalized) vectors."""
    return float(np.dot(a, b))
