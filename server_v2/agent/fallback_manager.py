"""
Fallback manager for coordinate tracking.

Python equivalent of OpenGuider's agent/fallback-manager.js.

Tracks the last known valid coordinates so that when the LLM returns
a suspicious jump or null, we can fall back to a recently-verified position.

Also detects anomalous coordinate jumps (>500px between consecutive frames).
"""

import logging
import math
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FallbackManager:
    """Tracks coordinate history and provides safe fallbacks.

    Usage:
        fm = FallbackManager(max_history=10)
        fm.record({"x": 320, "y": 450}, "executor_output")
        fallback = fm.get_fallback_coordinate()
    """

    def __init__(self, max_history: int = 10):
        self._history: List[dict] = []
        self._max_history = max_history

    @property
    def last_valid(self) -> Optional[dict]:
        """Get the most recent valid coordinate."""
        return self._history[-1] if self._history else None

    def record(self, coordinate: Optional[dict], reason: str = "") -> None:
        """Record a coordinate to the history.

        Args:
            coordinate: dict with 'x' and 'y' keys
            reason: Why this coordinate is being recorded
        """
        if not coordinate or not isinstance(coordinate, dict):
            return

        x = coordinate.get("x")
        y = coordinate.get("y")
        if x is None or y is None:
            return

        entry = {"x": x, "y": y, "reason": reason}
        self._history.append(entry)

        # Trim to max_history
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        logger.debug(f"Fallback recorded: ({x}, {y}) — {reason}")

    def get_fallback_coordinate(self, options: Optional[dict] = None) -> dict:
        """Get the safest available coordinate.

        Priority:
        1. Last valid recorded coordinate
        2. Screen center (500, 500 in 0-1000 or pixel center)

        Args:
            options: Optional dict with 'center_x' and 'center_y' overrides

        Returns:
            dict with 'x' and 'y' keys
        """
        if self._history:
            last = self._history[-1]
            logger.debug(f"Fallback: using last valid coord ({last['x']}, {last['y']})")
            return {"x": last["x"], "y": last["y"]}

        # Default to center
        if options:
            cx = options.get("center_x", 500)
            cy = options.get("center_y", 500)
        else:
            cx, cy = 500, 500

        logger.debug(f"Fallback: using center ({cx}, {cy})")
        return {"x": cx, "y": cy}

    def should_recheck(
        self,
        coordinate: Optional[dict],
        max_jump: float = 500.0,
    ) -> bool:
        """Check if a coordinate jump is suspiciously large.

        Args:
            coordinate: New coordinate to check
            max_jump: Maximum allowed distance jump

        Returns:
            True if the coordinate should be re-checked
        """
        if not coordinate or not self._history:
            return False

        last = self._history[-1]
        dx = coordinate.get("x", 0) - last.get("x", 0)
        dy = coordinate.get("y", 0) - last.get("y", 0)
        dist = math.sqrt(dx * dx + dy * dy)

        if dist > max_jump:
            logger.warning(
                f"Suspicious coordinate jump: {dist:.0f}px "
                f"from ({last['x']}, {last['y']}) to ({coordinate['x']}, {coordinate['y']})"
            )
            return True

        return False

    def analyze_jump(
        self,
        current: Optional[dict],
        max_distance: float = 500.0,
    ) -> dict:
        """Analyze the jump from last known coordinate.

        Returns:
            dict with: is_suspicious, distance, last_coordinate
        """
        if not current or not self._history:
            return {"is_suspicious": False, "distance": 0, "last_coordinate": None}

        last = self._history[-1]
        dx = current.get("x", 0) - last.get("x", 0)
        dy = current.get("y", 0) - last.get("y", 0)
        dist = math.sqrt(dx * dx + dy * dy)

        return {
            "is_suspicious": dist > max_distance,
            "distance": round(dist, 1),
            "last_coordinate": {"x": last["x"], "y": last["y"]},
        }

    def clear(self) -> None:
        """Clear all recorded coordinates."""
        self._history.clear()
        logger.debug("Fallback history cleared")

    def __len__(self) -> int:
        return len(self._history)
