"""
Prompt enricher — formats perception data into LLM prompt additions.

Python equivalent of OpenGuider's context/prompt-enricher.js.
Takes raw perception results and builds structured "ADDITIONAL CONTEXT"
sections for the LLM prompt.
"""

from typing import Optional, Any
from dataclasses import dataclass, field


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class EnrichContext:
    """All available context sources for prompt enrichment."""
    ocr_result: Any = None
    window_info: Any = None
    matched_elements: list = field(default_factory=list)
    ui_elements: list = field(default_factory=list)
    distilled_summary: str = ""


# ── Formatting helpers ────────────────────────────────────────────────────────


def format_ocr_elements(ocr_result, max_items: int = 30) -> str:
    """Format OCR words/lines with coordinates.

    Maps to OpenGuider's prompt-enricher.js formatOCRElements().
    """
    if not ocr_result:
        return ""

    if hasattr(ocr_result, 'words') and ocr_result.words:
        items = ocr_result.words[:max_items]
        lines = []
        for w in items:
            bbox = w.bbox if hasattr(w, 'bbox') else {}
            x = bbox.get('x0', 0) if isinstance(bbox, dict) else 0
            y = bbox.get('y0', 0) if isinstance(bbox, dict) else 0
            lines.append(f'  "{w.text}" @ ({x}, {y})')
        return "OCR words:\n" + "\n".join(lines)

    if hasattr(ocr_result, 'text') and ocr_result.text:
        return f"OCR text: {ocr_result.text[:300]}"

    return ""


def format_window_info(window_info) -> str:
    """Format focused window + visible windows + cursor.

    Maps to OpenGuider's prompt-enricher.js formatWindowInfo().
    """
    if not window_info:
        return ""

    parts = []

    if hasattr(window_info, 'focused_window') and window_info.focused_window:
        fw = window_info.focused_window
        parts.append(f"Focus: \"{fw.title}\"")
        if hasattr(fw, 'rect') and fw.rect:
            r = fw.rect
            parts[-1] += f" [{r.get('width', 0)}x{r.get('height', 0)}]"

    if hasattr(window_info, 'windows') and window_info.windows:
        visible = [w for w in window_info.windows if not getattr(w, 'minimized', False)]
        if visible:
            names = [f'"{w.title}"' for w in visible[:8]]
            parts.append(f"Visible: {', '.join(names)}")

    if hasattr(window_info, 'cursor_position') and window_info.cursor_position:
        cp = window_info.cursor_position
        parts.append(f"Cursor: ({cp[0]}, {cp[1]})")

    return " | ".join(parts)


def format_matched_elements(elements: list, max_items: int = 10) -> str:
    """Format matched elements with scores.

    Maps to OpenGuider's prompt-enricher.js formatMatchedElements().
    """
    if not elements:
        return ""

    items = []
    for el in elements[:max_items]:
        text = getattr(el, 'text', '') or str(el)
        score = getattr(el, 'score', 0)
        bbox = getattr(el, 'bbox', None)
        if bbox and isinstance(bbox, dict):
            items.append(f'  "{text}" @ ({bbox.get("x0", 0)}, {bbox.get("y0", 0)}) [score={score:.2f}]')
        else:
            items.append(f'  "{text}" [score={score:.2f}]')

    return "Matched elements:\n" + "\n".join(items) if items else ""


# ── Main enrichment function ──────────────────────────────────────────────────


def build_enriched_prompt(
    original_prompt: str,
    context: EnrichContext,
    use_distilled: bool = True,
) -> str:
    """Build an enriched prompt with screen context appended.

    Maps to OpenGuider's prompt-enricher.js buildEnrichedPrompt().

    The enriched prompt structure:
        {original_prompt}

        ---
        ADDITIONAL CONTEXT:
        {formatted context}

    Args:
        original_prompt: The user's original query/message
        context: EnrichContext with all perception sources
        use_distilled: Prefer distilled summary over raw data

    Returns:
        Enriched prompt string ready for LLM consumption
    """
    sections = []

    # Prefer distilled summary if available
    if use_distilled and context.distilled_summary:
        sections.append(context.distilled_summary)
    else:
        # Format raw perception data
        win = format_window_info(context.window_info)
        if win:
            sections.append(f"Windows: {win}")

        ocr = format_ocr_elements(context.ocr_result)
        if ocr:
            sections.append(ocr)

        matched = format_matched_elements(context.matched_elements)
        if matched:
            sections.append(matched)

    if not sections:
        return original_prompt

    context_block = "\n".join(sections)
    return f"{original_prompt}\n\n---\n[SYSTEM ANALYSIS OF SCREEN STATE]\n{context_block}"
