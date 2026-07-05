"""
Coordinate post-processing — validates and smooths LLM pointer coordinates.

Matches OpenGuider's interaction-pipeline.js postprocess() logic.
Pure Python, zero dependencies.
"""
from __future__ import annotations

# In-memory coordinate history for jump detection (shared across calls)
_history: list[dict] = []
_MAX_HISTORY = 5


def postprocess_pointer(
    norm_x: float,
    norm_y: float,
    label: str = "",
    screen_w: int = 1920,
    screen_h: int = 1080,
) -> dict:
    """
    Validate and optionally smooth a pointer coordinate from the LLM.

    Returns a dict with:
      - x, y: absolute screen pixel coords (clamped to screen bounds)
      - scaledX, scaledY: same as x, y (for overlay compatibility)
      - clamped: whether bounds clamping was applied
      - jumped: whether a suspicious jump was detected (>500px from last valid)
    """
    from server.services.validation.coords import normalize_coordinate, clamp_to_bounds

    # 1. Normalize 0-1000 -> absolute pixels
    abs_x, abs_y = normalize_coordinate(norm_x, norm_y, screen_w, screen_h)

    # 2. Clamp to screen bounds (10px margin)
    margin = 10
    abs_x, abs_y, clamped = clamp_to_bounds(abs_x, abs_y, screen_w, screen_h, margin)

    # 3. Jump detection — compare with coordinate history
    jumped = False
    if _history:
        last = _history[-1]
        dx = abs(abs_x - last["x"])
        dy = abs(abs_y - last["y"])
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 500:
            # Suspicious jump — fall back to historical average
            avg_x = sum(h["x"] for h in _history) / len(_history)
            avg_y = sum(h["y"] for h in _history) / len(_history)
            abs_x = int(round((abs_x + avg_x) / 2))  # Smooth: blend new with avg
            abs_y = int(round((abs_y + avg_y) / 2))
            jumped = True

    # 4. Record this coordinate
    _history.append({"x": abs_x, "y": abs_y, "label": label})
    if len(_history) > _MAX_HISTORY:
        _history.pop(0)

    return {
        "x": abs_x,
        "y": abs_y,
        "scaledX": abs_x,
        "scaledY": abs_y,
        "clamped": clamped,
        "jumped": jumped,
    }


def reset_history():
    """Clear coordinate history (call on session reset)."""
    global _history
    _history = []
