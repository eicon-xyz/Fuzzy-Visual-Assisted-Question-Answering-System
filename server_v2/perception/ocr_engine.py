"""
Tesseract OCR engine for local screen text recognition.

Python equivalent of OpenGuider's perception/ocr-engine.js.
Uses pytesseract (native Tesseract wrapper) instead of tesseract.js (WASM).

Provides word-level and line-level bounding boxes for downstream
element matching and coordinate verification.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from io import BytesIO

logger = logging.getLogger(__name__)

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    logger.warning("pytesseract or Pillow not installed. OCR will be unavailable.")


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class OCRWord:
    """A single recognized word with bounding box."""
    text: str
    bbox: dict  # {x0, y0, x1, y1, width, height}
    confidence: float = 0.0


@dataclass
class OCRLine:
    """A recognized text line with bounding box."""
    text: str
    bbox: dict  # {x0, y0, x1, y1, width, height}
    confidence: float = 0.0


@dataclass
class OCRResult:
    """Complete OCR result for an image."""
    text: str = ""
    words: List[OCRWord] = field(default_factory=list)
    lines: List[OCRLine] = field(default_factory=list)
    confidence: float = 0.0
    language: str = "eng"


# ── OCR Engine ────────────────────────────────────────────────────────────────


class OCREngine:
    """Lazy-initialized Tesseract OCR engine.

    OpenGuider counterpart: ocr-engine.js (Tesseract.createWorker("eng", 1))

    Usage:
        engine = OCREngine()
        result = await engine.recognize_from_base64(base64_string)
        # OR
        result = engine.recognize_from_bytes(image_bytes)
    """

    def __init__(self, lang: str = "eng"):
        self._lang = lang
        self._initialized = False

    @property
    def available(self) -> bool:
        return HAS_TESSERACT

    def _ensure_initialized(self):
        """Lazy init - only check availability, no worker to spin up."""
        if not self._initialized:
            if HAS_TESSERACT:
                logger.info(f"Tesseract OCR engine ready (lang={self._lang})")
            self._initialized = True

    def recognize_from_bytes(self, image_bytes: bytes) -> OCRResult:
        """Run OCR on raw image bytes (JPEG/PNG).

        Args:
            image_bytes: Raw image data

        Returns:
            OCRResult with words, lines, full text, and confidence
        """
        self._ensure_initialized()
        if not HAS_TESSERACT:
            logger.error("Tesseract not available. Returning empty OCRResult.")
            return OCRResult()

        try:
            image = Image.open(BytesIO(image_bytes))
            return self._recognize(image)
        except Exception as e:
            logger.error(f"OCR recognition failed: {e}")
            return OCRResult()

    def recognize_from_path(self, image_path: str) -> OCRResult:
        """Run OCR on an image file path.

        Args:
            image_path: Path to image file

        Returns:
            OCRResult with words, lines, full text, and confidence
        """
        self._ensure_initialized()
        if not HAS_TESSERACT:
            return OCRResult()

        try:
            image = Image.open(image_path)
            return self._recognize(image)
        except Exception as e:
            logger.error(f"OCR recognition from path failed: {e}")
            return OCRResult()

    def recognize_from_base64(self, image_b64: str) -> OCRResult:
        """Run OCR on a base64-encoded image string.

        Strips data URI prefix if present (data:image/...;base64,).

        Args:
            image_b64: Base64-encoded image (with or without data URI prefix)

        Returns:
            OCRResult with words, lines, full text, and confidence
        """
        import base64
        self._ensure_initialized()
        if not HAS_TESSERACT:
            return OCRResult()

        # Strip data URI prefix if present
        if image_b64.startswith("data:"):
            image_b64 = image_b64.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(image_b64)
            return self.recognize_from_bytes(image_bytes)
        except Exception as e:
            logger.error(f"OCR from base64 failed: {e}")
            return OCRResult()

    def _recognize(self, image: "Image.Image") -> OCRResult:
        """Internal recognition method using pytesseract."""
        # Get detailed data including bounding boxes
        data = pytesseract.image_to_data(image, lang=self._lang, output_type=pytesseract.Output.DICT)

        words = []
        lines = []
        line_texts = {}

        n = len(data.get("text", []))
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue

            conf = float(data["conf"][i]) if data["conf"][i] != "-1" else 0.0

            # Word-level
            if data["level"][i] == 5:  # word level
                word_entry = OCRWord(
                    text=text,
                    bbox={
                        "x0": data["left"][i],
                        "y0": data["top"][i],
                        "x1": data["left"][i] + data["width"][i],
                        "y1": data["top"][i] + data["height"][i],
                        "width": data["width"][i],
                        "height": data["height"][i],
                    },
                    confidence=conf,
                )
                words.append(word_entry)

            # Line-level (group by line_num)
            line_num = data["line_num"][i]
            if line_num not in line_texts:
                line_texts[line_num] = {"texts": [], "x0": 99999, "y0": 99999, "x1": 0, "y1": 0}
            lt = line_texts[line_num]
            lt["texts"].append(text)
            lt["x0"] = min(lt["x0"], data["left"][i])
            lt["y0"] = min(lt["y0"], data["top"][i])
            lt["x1"] = max(lt["x1"], data["left"][i] + data["width"][i])
            lt["y1"] = max(lt["y1"], data["top"][i] + data["height"][i])

        for line_num in sorted(line_texts.keys()):
            lt = line_texts[line_num]
            lines.append(OCRLine(
                text=" ".join(lt["texts"]),
                bbox={
                    "x0": lt["x0"],
                    "y0": lt["y0"],
                    "x1": lt["x1"],
                    "y1": lt["y1"],
                    "width": lt["x1"] - lt["x0"],
                    "height": lt["y1"] - lt["y0"],
                },
                confidence=sum(w.confidence for w in words if w.text in lt["texts"]) / max(1, len(lt["texts"])),
            ))

        # Overall confidence
        overall_conf = sum(w.confidence for w in words) / max(1, len(words)) if words else 0.0

        return OCRResult(
            text=" ".join(w.text for w in words),
            words=words,
            lines=lines,
            confidence=round(overall_conf, 1),
        )

    def terminate(self):
        """Cleanup (pytesseract has no persistent worker to terminate)."""
        self._initialized = False


# ── Module-level singleton ────────────────────────────────────────────────────

_default_engine: Optional[OCREngine] = None


def get_ocr_engine(lang: str = "eng") -> OCREngine:
    """Get or create the default OCR engine singleton."""
    global _default_engine
    if _default_engine is None:
        _default_engine = OCREngine(lang=lang)
    return _default_engine
