"""
Local Tesseract OCR engine — screen text extraction fallback.

Matches OpenGuider's src/perception/ocr-engine.js.
Supports English + Chinese text extraction with bounding boxes.
"""
from __future__ import annotations
import io
import base64
import logging
from typing import List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_initialized = False

# Common Tesseract install locations on Windows
_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\86178\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
]


@dataclass
class OCRWord:
    text: str
    bbox: dict  # {"x0": int, "y0": int, "x1": int, "y1": int}
    confidence: float


@dataclass
class OCRResult:
    text: str
    words: List[OCRWord] = field(default_factory=list)
    lines: List[OCRWord] = field(default_factory=list)
    confidence: float = 0.0


def _ensure_tesseract() -> bool:
    """Lazy initialization — ensure tesseract is available, set default paths."""
    global _initialized
    if _initialized:
        return True

    try:
        import pytesseract
        import os

        for p in _TESSERACT_PATHS:
            if os.path.exists(p):
                pytesseract.pytesseract.tesseract_cmd = p
                logger.info(f"Tesseract found at: {p}")
                break
        else:
            # Try to find via PATH
            logger.warning("Tesseract not found at known paths, trying PATH...")

        _initialized = True
        return True
    except ImportError:
        logger.warning("pytesseract not installed. Install with: pip install pytesseract")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Tesseract: {e}")
        return False


def _decode_image(image_base64: str):
    """Decode base64 image to PIL Image."""
    from PIL import Image

    raw = image_base64
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    img_bytes = base64.b64decode(raw)
    return Image.open(io.BytesIO(img_bytes))


def recognize_image(
    image_base64: str,
    language: str = "eng+chi_sim",
    min_confidence: float = 30.0,
) -> Optional[OCRResult]:
    """Run Tesseract OCR on a base64 image.

    Args:
        image_base64: Base64 encoded image (with or without data URI prefix)
        language: Tesseract language string (default: eng+chi_sim)
        min_confidence: Minimum word confidence (0-100)

    Returns:
        OCRResult with words/lines/text, or None on failure
    """
    if not _ensure_tesseract():
        return None

    try:
        import pytesseract
        from PIL import Image

        img = _decode_image(image_base64)

        # Get full text
        full_text = pytesseract.image_to_string(img, lang=language).strip()

        # Get word-level data with bounding boxes
        word_data = pytesseract.image_to_data(
            img, lang=language, output_type=pytesseract.Output.DICT,
        )

        words = []
        lines = []
        seen_lines = set()

        for i, text in enumerate(word_data.get("text", [])):
            text = text.strip()
            if not text:
                continue

            conf = float(word_data["conf"][i] if "conf" in word_data else 100)
            if conf < min_confidence:
                continue

            x = int(word_data["left"][i])
            y = int(word_data["top"][i])
            w = int(word_data["width"][i])
            h = int(word_data["height"][i])

            ocr_word = OCRWord(
                text=text,
                bbox={"x0": x, "y0": y, "x1": x + w, "y1": y + h},
                confidence=conf,
            )
            words.append(ocr_word)

            # Group by line number
            line_num = int(word_data.get("line_num", [0])[i])
            if line_num not in seen_lines:
                seen_lines.add(line_num)
                lines.append(ocr_word)

        return OCRResult(
            text=full_text,
            words=words,
            lines=lines,
            confidence=sum(w.confidence for w in words) / len(words) if words else 0,
        )
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return None


def ocr_text_only(image_base64: str, language: str = "eng+chi_sim") -> str:
    """Quick OCR — return text only, no bounding boxes."""
    if not _ensure_tesseract():
        return ""

    try:
        import pytesseract
        img = _decode_image(image_base64)
        return pytesseract.image_to_string(img, lang=language).strip()
    except Exception as e:
        logger.error(f"OCR text failed: {e}")
        return ""
