"""Local perception modules for screen understanding.

Replaces the external OmniParser HTTP microservice with:
- Tesseract OCR for text detection
- Windows UI Automation for control element scanning
- Win32 API for window enumeration
"""

from .ocr_engine import OCREngine, OCRResult, OCRWord, OCRLine, get_ocr_engine
from .ui_scanner import query_ui_automation, find_matching_elements, snap_to_nearest_element, calculate_element_center
from .window_enum import enumerate_active_app, get_active_windows, get_focused_window, get_cursor_position, WindowInfo, WindowRecord

__all__ = [
    "OCREngine",
    "OCRResult",
    "OCRWord",
    "OCRLine",
    "get_ocr_engine",
    "query_ui_automation",
    "find_matching_elements",
    "snap_to_nearest_element",
    "calculate_element_center",
    "enumerate_active_app",
    "get_active_windows",
    "get_focused_window",
    "get_cursor_position",
    "WindowInfo",
    "WindowRecord",
]
