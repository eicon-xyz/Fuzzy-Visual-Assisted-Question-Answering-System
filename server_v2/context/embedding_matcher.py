"""
Semantic embedding matcher using MiniLM for UI element matching.

Python equivalent of OpenGuider's context/embedding-matcher.js.
Uses sentence-transformers (native Python) instead of @xenova/transformers (WASM).

Model: all-MiniLM-L6-v2 (384-dim embeddings)
Provides cosine similarity, euclidean distance, and top-K matching.
"""

import logging
import math
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except Exception:
    HAS_SENTENCE_TRANSFORMERS = False
    import logging
    logging.getLogger(__name__).warning(
        "sentence-transformers not available. Embedding matching will use keyword fallback."
    )


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class EmbeddedElement:
    """An element with its text embedding and original data."""
    text: str
    embedding: Optional[List[float]] = None
    element: Any = None  # Original OCRWord / UIAElement / dict
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchResult:
    """Result of a semantic match query."""
    element: Any
    text: str
    score: float  # 0.0 - 1.0 cosine similarity
    distance: float = 0.0  # Euclidean distance (lower is better)
    rank: int = 0


# ── Embedding model ───────────────────────────────────────────────────────────

_embedding_model = None


def _load_embedding_model() -> Optional["SentenceTransformer"]:
    """Lazy-load the MiniLM embedding model.

    Maps to OpenGuider's embedding-matcher.js loadEmbeddingModel().
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    if not HAS_SENTENCE_TRANSFORMERS:
        return None

    try:
        model_name = "all-MiniLM-L6-v2"
        _embedding_model = SentenceTransformer(model_name)
        logger.info(f"Embedding model loaded: {model_name}")
        return _embedding_model
    except Exception as e:
        logger.warning(f"Failed to load embedding model: {e}")
        return None


# ── Vector operations ─────────────────────────────────────────────────────────


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors.

    Maps to OpenGuider's embedding-matcher.js cosineSimilarity().
    """
    if not a or not b or len(a) != len(b):
        return 0.0

    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def euclidean_distance(a: List[float], b: List[float]) -> float:
    """Compute Euclidean distance between two vectors.

    Maps to OpenGuider's embedding-matcher.js euclideanDistance().
    """
    if not a or not b or len(a) != len(b):
        return float("inf")

    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


# ── Embedding helpers ─────────────────────────────────────────────────────────


def get_embedding(text: str) -> Optional[List[float]]:
    """Get embedding vector for a single text string.

    Maps to OpenGuider's embedding-matcher.js getEmbedding().
    """
    model = _load_embedding_model()
    if model is None or not text or not text.strip():
        return None

    try:
        embedding = model.encode(text.strip(), normalize_embeddings=True)
        return embedding.tolist()
    except Exception as e:
        logger.error(f"Embedding failed for '{text[:50]}': {e}")
        return None


def get_batch_embeddings(texts: List[str]) -> List[Optional[List[float]]]:
    """Get embeddings for a batch of texts.

    Maps to OpenGuider's embedding-matcher.js getBatchEmbeddings().

    Returns:
        List of embedding vectors (None for failed items)
    """
    model = _load_embedding_model()
    if model is None:
        return [None] * len(texts)

    valid_texts = [t.strip() for t in texts]
    if not valid_texts:
        return [None] * len(texts)

    try:
        embeddings = model.encode(valid_texts, normalize_embeddings=True)
        return [e.tolist() for e in embeddings]
    except Exception as e:
        logger.error(f"Batch embedding failed: {e}")
        return [None] * len(texts)


def embed_elements(
    elements: List[Any],
    label_field: str = "text",
) -> List[EmbeddedElement]:
    """Embed a list of elements for semantic matching.

    Maps to OpenGuider's embedding-matcher.js embedElements().

    Args:
        elements: List of objects with a text field (OCRWord, OCRLine, UIAElement, or dict)
        label_field: Attribute name containing text to embed

    Returns:
        List of EmbeddedElement with embeddings attached
    """
    # Extract texts
    texts = []
    for el in elements:
        if isinstance(el, dict):
            texts.append(str(el.get(label_field, "")))
        elif hasattr(el, label_field):
            texts.append(str(getattr(el, label_field, "")))
        else:
            texts.append(str(el))

    # Batch embed
    embeddings = get_batch_embeddings(texts)

    # Build EmbeddedElements
    result = []
    for i, (el, text) in enumerate(zip(elements, texts)):
        emb = embeddings[i] if i < len(embeddings) else None
        result.append(EmbeddedElement(
            text=text,
            embedding=emb,
            element=el,
        ))
    return result


# ── Matching ──────────────────────────────────────────────────────────────────


def find_best_match(
    query: str,
    candidates: List[EmbeddedElement],
    min_score: float = 0.3,
) -> Optional[MatchResult]:
    """Find the single best matching element for a query.

    Args:
        query: Search query text
        candidates: Pre-embedded candidate elements
        min_score: Minimum cosine similarity threshold

    Returns:
        Best MatchResult or None
    """
    matches = find_top_matches(query, candidates, top_k=1, min_score=min_score)
    return matches[0] if matches else None


def find_top_matches(
    query: str,
    candidates: List[EmbeddedElement],
    top_k: int = 5,
    min_score: float = 0.3,
) -> List[MatchResult]:
    """Find top-K matching elements for a query via semantic search.

    Maps to OpenGuider's embedding-matcher.js findTopMatches().

    Falls back to keyword substring matching if embeddings unavailable.

    Args:
        query: Search query text
        candidates: Pre-embedded candidate elements
        top_k: Number of top results to return
        min_score: Minimum cosine similarity threshold

    Returns:
        Sorted list of MatchResult (best first)
    """
    if not candidates:
        return []

    query_embedding = get_embedding(query)

    # If no embedding model, fall back to keyword matching
    if query_embedding is None:
        return _keyword_match(query, candidates, top_k)

    results = []
    for i, candidate in enumerate(candidates):
        if candidate.embedding is None:
            continue

        score = cosine_similarity(query_embedding, candidate.embedding)
        dist = euclidean_distance(query_embedding, candidate.embedding)

        if score >= min_score:
            results.append(MatchResult(
                element=candidate.element,
                text=candidate.text,
                score=round(score, 4),
                distance=round(dist, 4),
                rank=0,  # set after sorting
            ))

    # Sort by score descending
    results.sort(key=lambda r: r.score, reverse=True)

    # Assign ranks
    for i, r in enumerate(results[:top_k]):
        r.rank = i + 1

    return results[:top_k]


def _keyword_match(
    query: str,
    candidates: List[EmbeddedElement],
    top_k: int = 5,
) -> List[MatchResult]:
    """Fallback keyword/substring matching when embeddings are unavailable."""
    query_lower = query.lower()
    results = []

    for i, candidate in enumerate(candidates):
        text_lower = candidate.text.lower()
        if not text_lower:
            continue

        # Score: exact match > substring > initial char match
        if query_lower == text_lower:
            score = 1.0
        elif query_lower in text_lower or text_lower in query_lower:
            score = 0.7
        elif text_lower.startswith(query_lower[:3]):
            score = 0.4
        else:
            continue

        results.append(MatchResult(
            element=candidate.element,
            text=candidate.text,
            score=score,
            distance=1.0 - score,
            rank=0,
        ))

    results.sort(key=lambda r: r.score, reverse=True)
    for i, r in enumerate(results[:top_k]):
        r.rank = i + 1

    return results[:top_k]
