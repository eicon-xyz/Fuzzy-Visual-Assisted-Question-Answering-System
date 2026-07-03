"""
Semantic coordinate verification using embedding similarity.

Python equivalent of OpenGuider's validation/semantic-verifier.js.

After the LLM returns a coordinate with a label (e.g., "click the
Settings button at (320, 450)"), this module checks whether the
nearby UI elements actually match the label semantically.

Uses MiniLM embeddings + Levenshtein distance as fallback.
"""

import logging
from typing import List, Optional, Any, Tuple
from dataclasses import dataclass

from context.embedding_matcher import (
    find_best_match,
    embed_elements,
    cosine_similarity,
    get_embedding,
    EmbeddedElement,
)

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class VerificationResult:
    """Result of semantic coordinate verification."""
    verified: bool
    score: float = 0.0
    reason: str = ""
    best_match_text: str = ""
    best_match_element: Any = None


# ── Levenshtein distance (fallback when embeddings unavailable) ────────────────


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def _levenshtein_similarity(s1: str, s2: str) -> float:
    """Levenshtein distance normalized to 0-1 similarity score."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    max_len = max(len(s1), len(s2))
    dist = _levenshtein(s1.lower(), s2.lower())
    return 1.0 - (dist / max_len)


# ── Main verification ──────────────────────────────────────────────────────────


def verify_coordinate_with_elements(
    coordinate: Optional[dict],
    label: Optional[str],
    elements: List[Any],
    tolerance: int = 100,
    threshold: float = 0.6,
) -> VerificationResult:
    """Verify that a coordinate's semantic context matches the given label.

    Maps to OpenGuider's semantic-verifier.js verifyCoordinateWithElements().

    Process:
    1. Find elements within `tolerance` pixels of the coordinate
    2. Embed the label and nearby element names
    3. Find best match via cosine similarity
    4. Fall back to Levenshtein if embeddings unavailable

    Args:
        coordinate: {x, y} dict with absolute pixel coords
        label: Expected element label (from LLM step instruction)
        elements: List of UIAElement or UIAElement-like objects (must have rect + name/text)
        tolerance: Max pixel distance to consider "nearby"
        threshold: Minimum similarity score to consider "verified"

    Returns:
        VerificationResult with verified flag, score, and best match info
    """
    if not coordinate or not label or not elements:
        return VerificationResult(
            verified=False,
            score=0.0,
            reason="Missing coordinate, label, or elements",
        )

    cx = coordinate.get("x", 0)
    cy = coordinate.get("y", 0)

    # Find nearby elements
    nearby = []
    for el in elements:
        rect = getattr(el, "rect", None) or {}
        if not rect:
            continue

        rx = rect.get("x", 0)
        ry = rect.get("y", 0)
        rw = rect.get("width", 0)
        rh = rect.get("height", 0)
        rx1 = rect.get("x1", rx + rw)
        ry1 = rect.get("y1", ry + rh)

        # Check if coordinate is within tolerance of element bounds
        if (
            rx - tolerance <= cx <= rx1 + tolerance
            and ry - tolerance <= cy <= ry1 + tolerance
        ):
            # Get element text
            text = (
                getattr(el, "name", "")
                or getattr(el, "text", "")
                or str(el)
            )
            if text.strip():
                nearby.append(el)

    if not nearby:
        return VerificationResult(
            verified=False,
            score=0.0,
            reason=f"No elements within {tolerance}px of ({cx}, {cy})",
        )

    # Extract texts
    texts = []
    for el in nearby:
        text = getattr(el, "name", "") or getattr(el, "text", "") or str(el)
        texts.append(text.strip())

    # Try embedding-based matching
    label_embedding = get_embedding(label)
    if label_embedding is not None:
        embedded_elements = embed_elements(nearby, label_field="name")

        best_score = 0.0
        best_el = None
        best_text = ""

        for ee in embedded_elements:
            if ee.embedding is None:
                # Fall back to Levenshtein for this element
                score = _levenshtein_similarity(label, ee.text)
            else:
                score = cosine_similarity(label_embedding, ee.embedding)

            if score > best_score:
                best_score = score
                best_el = ee.element
                best_text = ee.text

        verified = best_score >= threshold
        return VerificationResult(
            verified=verified,
            score=round(best_score, 4),
            reason=(
                f"Best match: '{best_text}' (score={best_score:.2f})"
                if verified
                else f"No good match for '{label}' near ({cx}, {cy}). Best: '{best_text}' ({best_score:.2f})"
            ),
            best_match_text=best_text,
            best_match_element=best_el,
        )
    else:
        # Pure Levenshtein fallback
        best_score = 0.0
        best_el = None
        best_text = ""

        for el, text in zip(nearby, texts):
            score = _levenshtein_similarity(label, text)
            if score > best_score:
                best_score = score
                best_el = el
                best_text = text

        verified = best_score >= threshold
        return VerificationResult(
            verified=verified,
            score=round(best_score, 4),
            reason=(
                f"Best match (Levenshtein): '{best_text}' (score={best_score:.2f})"
                if verified
                else f"No Levenshtein match for '{label}' near ({cx}, {cy})"
            ),
            best_match_text=best_text,
            best_match_element=best_el,
        )


def verify_with_ocr(
    ocr_result,
    coordinate: dict,
    tolerance: int = 50,
) -> VerificationResult:
    """Verify coordinate against OCR text at that position.

    Maps to OpenGuider's semantic-verifier.js verifyWithOCR().

    Checks if there's any OCR-detected text near the coordinate.

    Args:
        ocr_result: OCRResult from perception/ocr_engine.py
        coordinate: {x, y} dict
        tolerance: Max pixel distance

    Returns:
        VerificationResult
    """
    if not ocr_result or not coordinate:
        return VerificationResult(verified=False, score=0.0, reason="No OCR data")

    cx = coordinate.get("x", 0)
    cy = coordinate.get("y", 0)

    words = getattr(ocr_result, "words", []) or []
    for word in words:
        bbox = getattr(word, "bbox", {}) or {}
        x0 = bbox.get("x0", 0)
        y0 = bbox.get("y0", 0)
        x1 = bbox.get("x1", 0)
        y1 = bbox.get("y1", 0)

        if (
            x0 - tolerance <= cx <= x1 + tolerance
            and y0 - tolerance <= cy <= y1 + tolerance
        ):
            return VerificationResult(
                verified=True,
                score=1.0,
                reason=f"OCR text found: '{word.text}' at ({x0}, {y0})",
                best_match_text=word.text,
            )

    return VerificationResult(
        verified=False,
        score=0.0,
        reason=f"No OCR text within {tolerance}px of ({cx}, {cy})",
    )
