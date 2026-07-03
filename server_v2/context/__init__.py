"""Context awareness layer for screen perception enrichment."""

from .embedding_matcher import (
    EmbeddedElement,
    MatchResult,
    embed_elements,
    find_best_match,
    find_top_matches,
    get_embedding,
    get_batch_embeddings,
    cosine_similarity,
)
from .context_analyzer import (
    PerceptionContext,
    analyze_context,
    build_raw_context_string,
)
from .prompt_enricher import (
    EnrichContext,
    build_enriched_prompt,
    format_ocr_elements,
    format_window_info,
    format_matched_elements,
)

__all__ = [
    "EmbeddedElement",
    "MatchResult",
    "embed_elements",
    "find_best_match",
    "find_top_matches",
    "get_embedding",
    "get_batch_embeddings",
    "cosine_similarity",
    "PerceptionContext",
    "analyze_context",
    "build_raw_context_string",
    "EnrichContext",
    "build_enriched_prompt",
    "format_ocr_elements",
    "format_window_info",
    "format_matched_elements",
]
