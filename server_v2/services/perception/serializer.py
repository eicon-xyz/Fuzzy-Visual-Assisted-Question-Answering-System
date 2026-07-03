"""
UI element serializer — converts perception output to LLM prompt text.

Extended from the original OmniParser-only serializer to handle:
- OmniParser UI elements (backward compatible)
- OCR results (words + lines with bounding boxes)
- Window enumeration (focused + visible windows)
- UI Automation elements (control type, name, automation id)

Maps to OpenGuider's context/prompt-enricher.js + perception/serializer.js.
"""

from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from server_v2.models.schemas import UIElement


def serialize_elements(elements: List["UIElement"], max_count: int = 25) -> str:
    """
    Serialize UI element list to LLM prompt text.

    Args:
        elements: OmniParser/OCR UI element list
        max_count: Max elements to include (token budget control)

    Returns:
        Formatted element description text
    """
    if not elements:
        return "（未检测到 UI 元素）"

    sorted_els = sorted(elements, key=lambda e: e.confidence, reverse=True)[:max_count]
    lines = []
    for e in sorted_els:
        text = e.text.strip() if e.text else "(无文本)"
        lines.append(
            f"  {e.element_id}: {e.element_type} \"{text}\" (置信度:{e.confidence:.2f})"
        )
    return "\n".join(lines)


# ── New: unified perception serializers ──────────────────────────────────────


def serialize_ocr_result(ocr_result, max_lines: int = 30) -> str:
    """Serialize OCR result to prompt text.

    Maps to OpenGuider's prompt-enricher.js formatOCRElements().

    Args:
        ocr_result: OCRResult from perception/ocr_engine.py
        max_lines: Max text lines to include

    Returns:
        Formatted OCR text description
    """
    if not ocr_result:
        return "（未检测到屏幕文字）"

    parts = []
    if ocr_result.lines:
        parts.append(f"屏幕文字（{len(ocr_result.lines)} 行，置信度 {ocr_result.confidence:.1f}%）:")
        for line in ocr_result.lines[:max_lines]:
            bbox = line.bbox
            parts.append(
                f"  \"{line.text}\" @ ({bbox.get('x0', 0)}, {bbox.get('y0', 0)})"
                f" - ({bbox.get('x1', 0)}, {bbox.get('y1', 0)})"
            )
    elif ocr_result.text:
        parts.append(f"屏幕文字: \"{ocr_result.text[:500]}\"")
    else:
        parts.append("（未检测到屏幕文字）")

    return "\n".join(parts)


def serialize_window_info(window_info) -> str:
    """Serialize window enumeration to prompt text.

    Maps to OpenGuider's prompt-enricher.js formatWindowInfo().

    Args:
        window_info: WindowInfo from perception/window_enum.py

    Returns:
        Formatted window state description
    """
    if not window_info:
        return "（无法获取窗口信息）"

    parts = []

    # Focused window
    if window_info.focused_window:
        fw = window_info.focused_window
        parts.append(f"当前活动窗口: \"{fw.title}\"")
        r = fw.rect
        parts.append(
            f"  位置: ({r.get('x', 0)}, {r.get('y', 0)}), "
            f"大小: {r.get('width', 0)}x{r.get('height', 0)}"
        )

    # Visible windows
    if window_info.windows:
        visible = [w for w in window_info.windows if not w.minimized]
        if visible:
            parts.append(f"可见窗口 ({len(visible)} 个):")
            for w in visible[:10]:
                parts.append(f"  - \"{w.title}\" (pid={w.pid})")

    # Cursor position
    if window_info.cursor_position:
        cx, cy = window_info.cursor_position
        parts.append(f"鼠标位置: ({cx}, {cy})")

    return "\n".join(parts) if parts else "（无可见窗口）"


def serialize_uia_elements(elements, max_count: int = 25) -> str:
    """Serialize UI Automation elements to prompt text.

    Maps to OpenGuider's prompt-enricher.js formatMatchedElements().

    Args:
        elements: List of UIAElement from perception/ui_scanner.py
        max_count: Max elements to include

    Returns:
        Formatted UIA element description
    """
    if not elements:
        return "（未检测到 UI 控件）"

    sorted_els = sorted(
        elements,
        key=lambda e: (e.rect.get("width", 0) * e.rect.get("height", 0)),
        reverse=True,
    )[:max_count]

    parts = [f"桌面 UI 控件 ({len(sorted_els)} 个):"]
    for e in sorted_els:
        r = e.rect
        parts.append(
            f"  {e.element_id}: {e.control_type} \"{e.name}\""
            f" @ ({r.get('x', 0)}, {r.get('y', 0)})"
            f" {r.get('width', 0)}x{r.get('height', 0)}"
        )

    return "\n".join(parts)


def serialize_perception(
    ocr_result=None,
    window_info=None,
    uia_elements=None,
    ui_elements=None,
) -> str:
    """Unified perception serializer: combine all perception sources.

    Maps to OpenGuider's prompt-enricher.js buildEnrichedPrompt().

    Args:
        ocr_result: OCRResult from OCR engine
        window_info: WindowInfo from window enumeration
        uia_elements: List of UIAElement from UI scanner
        ui_elements: List of UIElement from OmniParser (backward compat)

    Returns:
        Combined perception text for LLM context
    """
    sections = []

    # Window info
    win_text = serialize_window_info(window_info)
    if win_text and "无法获取" not in win_text:
        sections.append(win_text)

    # OCR text
    if ocr_result:
        ocr_text = serialize_ocr_result(ocr_result, max_lines=30)
        if ocr_text and "未检测到" not in ocr_text:
            sections.append(ocr_text)

    # UIA elements
    if uia_elements:
        uia_text = serialize_uia_elements(uia_elements, max_count=25)
        if uia_text and "未检测到" not in uia_text:
            sections.append(uia_text)

    # OmniParser elements (backward compatible)
    if ui_elements:
        omni_text = serialize_elements(ui_elements, max_count=25)
        if omni_text and "未检测到" not in omni_text:
            sections.append(omni_text)

    if not sections:
        return "（屏幕状态：无可用的感知数据）"

    return "[屏幕状态]\n" + "\n\n".join(sections)
