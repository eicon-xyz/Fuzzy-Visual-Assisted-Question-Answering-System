"""
Interaction pipeline — preprocess/LLM/postprocess sandwich.

Python equivalent of OpenGuider's agent/interaction-pipeline.js.

Wraps every LLM guidance call with:
  PREPROCESS: OCR + window enumeration + embedding matching → context distillation
  POSTPROCESS: bounds validation → UIA snap → semantic verification → confidence

This is the core of the "aware assistance" system — it enriches the LLM's
understanding of what's on screen and validates what the LLM returns.
"""

import logging
from typing import Any, Dict, List, Optional

from agent.fallback_manager import FallbackManager

logger = logging.getLogger(__name__)


class InteractionPipeline:
    """Preprocess → LLM → Postprocess sandwich for screen-aware guidance.

    Maps to OpenGuider's agent/interaction-pipeline.js InteractionPipeline.

    Usage:
        pipeline = InteractionPipeline()
        pre_ctx = await pipeline.preprocess(images, step, session_id)
        # ... LLM call happens here ...
        result = await pipeline.postprocess(coordinate, label, step, session_id)
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.fallback_manager = FallbackManager(max_history=10)

        # Cached perception results
        self._ocr_result = None
        self._window_info = None
        self._ui_elements: List = []
        self._matched_elements: List = []

    def set_enabled(self, enabled: bool) -> None:
        """Toggle the entire pipeline on/off."""
        self.enabled = enabled
        if not enabled:
            self.clear()

    # ── Preprocess ───────────────────────────────────────────────────────────

    async def preprocess(
        self,
        images: List[Dict],
        step: Optional[Dict] = None,
        session_id: str = "",
    ) -> Dict:
        """Run perception on screenshots before the LLM call.

        Maps to OpenGuider's interaction-pipeline.js preprocess().

        1. OCR the screenshot
        2. Enumerate active windows
        3. Match UI elements to step instruction via embeddings

        Args:
            images: List of screenshot dicts [{base64Jpeg, width, height}]
            step: Current plan step dict (optional)
            session_id: Session ID for element caching

        Returns:
            Dict with ocr_result, window_info, matched_elements
        """
        if not self.enabled:
            return {"ocr_result": None, "window_info": None, "matched_elements": []}

        ocr_result = None
        window_info = None
        matched_elements = []

        try:
            # 1. OCR
            if images and len(images) > 0:
                from perception.ocr_engine import get_ocr_engine

                img = images[0]
                b64 = img.get("base64Jpeg", img.get("base64", ""))
                if b64:
                    engine = get_ocr_engine()
                    ocr_result = engine.recognize_from_base64(b64)
                    self._ocr_result = ocr_result
                    logger.debug(
                        f"OCR: {len(ocr_result.words)} words, "
                        f"{len(ocr_result.lines)} lines, "
                        f"confidence={ocr_result.confidence:.1f}%"
                    )

            # 2. Window enumeration
            from perception.window_enum import enumerate_active_app

            window_info = enumerate_active_app()
            self._window_info = window_info
            if window_info and window_info.focused_window:
                logger.debug(f"Focused window: '{window_info.focused_window.title}'")

            # 3. Element matching (if we have a step instruction)
            if step and step.get("instruction") and ocr_result:
                instruction = step["instruction"]
                matched_elements = await self._find_matching_elements(
                    instruction, ocr_result
                )
                self._matched_elements = matched_elements
                logger.debug(f"Matched {len(matched_elements)} elements for instruction")

        except Exception as e:
            logger.error(f"Preprocess error: {e}")

        return {
            "ocr_result": ocr_result,
            "window_info": window_info,
            "matched_elements": matched_elements,
        }

    async def _find_matching_elements(
        self,
        query: str,
        ocr_result,
    ) -> List[Dict]:
        """Find OCR words/lines matching the step instruction via embeddings."""
        from context.embedding_matcher import embed_elements, find_top_matches

        candidates = []

        # Collect OCR words as candidates
        if hasattr(ocr_result, "words"):
            for word in ocr_result.words:
                if word.text and word.text.strip():
                    candidates.append(word)

        # Collect OCR lines as candidates
        if hasattr(ocr_result, "lines"):
            for line in ocr_result.lines:
                if line.text and line.text.strip():
                    candidates.append(line)

        if not candidates:
            return []

        # Embed and match
        embedded = embed_elements(candidates, label_field="text")
        matches = find_top_matches(query, embedded, top_k=10, min_score=0.3)

        # Convert to dict format
        results = []
        for m in matches:
            el = m.element
            bbox = getattr(el, "bbox", None) or {}
            results.append({
                "text": m.text,
                "score": m.score,
                "bbox": {
                    "x0": bbox.get("x0", 0) if isinstance(bbox, dict) else 0,
                    "y0": bbox.get("y0", 0) if isinstance(bbox, dict) else 0,
                    "x1": bbox.get("x1", 0) if isinstance(bbox, dict) else 0,
                    "y1": bbox.get("y1", 0) if isinstance(bbox, dict) else 0,
                },
            })

        return results

    # ── Context distillation ─────────────────────────────────────────────────

    async def distill_context(
        self,
        original_prompt: str,
        pre_context: Dict,
        settings: Any = None,
    ) -> str:
        """Distill raw perception data into a concise text summary.

        Maps to OpenGuider's interaction-pipeline.js distillContext().
        """
        if not self.enabled:
            return original_prompt

        from context.context_analyzer import PerceptionContext, analyze_context

        ctx = PerceptionContext(
            ocr_result=pre_context.get("ocr_result"),
            window_info=pre_context.get("window_info"),
            matched_elements=pre_context.get("matched_elements", []),
            ui_elements=self._ui_elements,
        )

        try:
            summary = await analyze_context(original_prompt, ctx, settings)
            if summary:
                return f"{original_prompt}\n\n---\n[SYSTEM ANALYSIS OF SCREEN STATE]\n{summary}"
        except Exception as e:
            logger.warning(f"Context distillation failed: {e}")

        return original_prompt

    # ── Postprocess ──────────────────────────────────────────────────────────

    async def postprocess(
        self,
        coordinate: Optional[Dict],
        label: Optional[str],
        step: Optional[Dict] = None,
        session_id: str = "",
        options: Optional[Dict] = None,
    ) -> Dict:
        """Validate and enhance LLM output coordinates.

        Maps to OpenGuider's interaction-pipeline.js postprocess().

        1. Bounds validation — clamp to screen
        2. UIA element query — find desktop controls
        3. Snap to nearest element (≤30px)
        4. Semantic verification via embeddings

        Args:
            coordinate: {x, y} dict from LLM (absolute or 0-1000)
            label: Element label from LLM
            step: Current step dict
            session_id: Session ID
            options: Optional overrides

        Returns:
            Dict with coordinate, verified, reason, confidence, snapped
        """
        if not self.enabled:
            return {
                "coordinate": coordinate,
                "verified": True,
                "reason": "pipeline disabled",
                "confidence": 1.0,
            }

        validated_coordinate = dict(coordinate) if coordinate else None
        verification = None
        bounds_check = None
        snapped = None

        try:
            logger.debug(
                f"Postprocess: coord=({coordinate.get('x') if coordinate else '?'}, "
                f"{coordinate.get('y') if coordinate else '?'}), label='{label or ''}'"
            )

            # 1. Bounds validation
            from validation.bounds_validator import validate_coordinate

            bounds_check = validate_coordinate(coordinate)
            logger.debug(
                f"Bounds: valid={bounds_check.valid}, "
                f"reason={bounds_check.reason}"
            )

            if not bounds_check.valid and bounds_check.clamped:
                validated_coordinate = bounds_check.clamped
                logger.debug(
                    f"Clamped to ({validated_coordinate['x']}, {validated_coordinate['y']})"
                )

            # 2. UIA element query
            from perception.ui_scanner import (
                query_ui_automation,
                find_matching_elements,
                snap_to_nearest_element,
            )

            self._ui_elements = query_ui_automation(max_elements=5000)
            logger.debug(f"UIA elements: {len(self._ui_elements)}")

            # 3. Snap to nearest matching element
            if self._ui_elements and coordinate and label:
                matched = find_matching_elements(label, self._ui_elements)
                logger.debug(f"Matched {len(matched)} UIA elements for '{label}'")

                if matched:
                    # Convert coordinate to pixel tuple for snap
                    coord_tuple = (
                        int(coordinate.get("x", 0)),
                        int(coordinate.get("y", 0)),
                    )
                    snap_result = snap_to_nearest_element(
                        coord_tuple, matched, tolerance=30
                    )

                    if snap_result and snap_result.distance <= 30:
                        snapped = {
                            "element": snap_result.element,
                            "snapped_coordinate": snap_result.snapped_coordinate,
                            "distance": snap_result.distance,
                        }
                        validated_coordinate = {
                            "x": snap_result.snapped_coordinate[0],
                            "y": snap_result.snapped_coordinate[1],
                        }
                        logger.debug(
                            f"Snapped: ({validated_coordinate['x']}, "
                            f"{validated_coordinate['y']}), "
                            f"dist={snap_result.distance:.1f}px"
                        )
                    else:
                        logger.debug("Snap distance too large, using raw coords")

            # 4. Semantic verification
            if validated_coordinate and label:
                from validation.semantic_verifier import verify_coordinate_with_elements

                verification = verify_coordinate_with_elements(
                    validated_coordinate,
                    label,
                    self._ui_elements,
                    tolerance=100,
                )
                logger.debug(
                    f"Verification: verified={verification.verified}, "
                    f"score={verification.score:.2f}, "
                    f"reason={verification.reason}"
                )

        except Exception as e:
            logger.error(f"Postprocess error: {e}")

        # Record to fallback manager
        if validated_coordinate:
            self.fallback_manager.record(validated_coordinate, "postprocess")

        # Calculate confidence
        confidence = self._calculate_confidence(bounds_check, verification, snapped)

        return {
            "coordinate": validated_coordinate,
            "verified": verification.verified if verification else False,
            "reason": (
                verification.reason
                if verification
                else (bounds_check.reason if bounds_check else "unknown")
            ),
            "confidence": confidence,
            "snapped": snapped,
            "bounds_clamped": bool(bounds_check and bounds_check.clamped),
        }

    def _calculate_confidence(
        self,
        bounds_check=None,
        verification=None,
        snapped=None,
    ) -> float:
        """Calculate overall confidence in the coordinate.

        Maps to OpenGuider's interaction-pipeline.js calculateConfidence().
        """
        confidence = 0.7  # Base: trust raw LLM output

        if bounds_check and bounds_check.valid:
            confidence += 0.15

        if verification and verification.verified and verification.score > 0.8:
            confidence += 0.15

        return round(min(1.0, max(0.0, confidence)), 2)

    # ── Fallback ─────────────────────────────────────────────────────────────

    def get_fallback_coordinate(self) -> Optional[Dict]:
        """Get last known valid coordinate as fallback."""
        return self.fallback_manager.get_fallback_coordinate()

    def should_recheck(self, coordinate: Optional[Dict]) -> bool:
        """Check if a coordinate needs re-verification."""
        return self.fallback_manager.should_recheck(coordinate)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def clear(self, session_id: str = "") -> None:
        """Clear cached perception data."""
        self._ocr_result = None
        self._window_info = None
        self._ui_elements = []
        self._matched_elements = []
        if session_id:
            self.fallback_manager.clear()
