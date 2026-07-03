"""
Coordinate bounds validation for post-LLM verification.

Python equivalent of OpenGuider's validation/bounds-validator.js.
Validates that coordinates are within display bounds and clamps
out-of-range values. Operates in both 0-1000 normalized space
and absolute pixel space.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Result of coordinate bounds validation."""
    valid: bool
    reason: str = ""
    clamped: Optional[dict] = None  # {x, y} if clamping was needed
    display: Optional[dict] = None  # {width, height} of target display


# ── Validation ────────────────────────────────────────────────────────────────


def validate_coordinate(
    coordinate: Optional[dict],
    display_bounds: Optional[dict] = None,
    allow_out_of_bounds: bool = False,
) -> ValidationResult:
    """Validate a coordinate is within display bounds.

    Maps to OpenGuider's bounds-validator.js validateCoordinate().

    Supports both 0-1000 normalized and raw pixel coordinates.
    Detection heuristic: if x <= 1000 and y <= 1000, treat as 0-1000 range.

    Args:
        coordinate: dict with 'x' and 'y' keys
        display_bounds: optional dict with 'width' and 'height'
        allow_out_of_bounds: if True, allow negative/oversized coords

    Returns:
        ValidationResult with valid flag, reason, and clamped coord if needed
    """
    if not coordinate or not isinstance(coordinate, dict):
        return ValidationResult(valid=False, reason="No coordinate provided")

    x = coordinate.get("x")
    y = coordinate.get("y")

    if x is None or y is None:
        return ValidationResult(valid=False, reason="Missing x or y coordinate")

    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return ValidationResult(valid=False, reason=f"Invalid coordinate types: x={type(x).__name__}, y={type(y).__name__}")

    # Determine coordinate space
    max_w = (display_bounds or {}).get("width", 1920)
    max_h = (display_bounds or {}).get("height", 1080)

    # Detect normalized vs pixel space
    if 0 < x <= 1000 and 0 < y <= 1000 and max_w > 1000:
        # Normalized 0-1000 space
        min_x, max_x = 0.0, 1000.0
        min_y, max_y = 0.0, 1000.0
        space = "0-1000"
    else:
        # Pixel space
        min_x, max_x = -100.0, float(max_w + 100)
        min_y, max_y = -100.0, float(max_h + 100)
        space = "pixel"

    if allow_out_of_bounds:
        return ValidationResult(
            valid=True,
            reason="allow_out_of_bounds=True",
            display={"width": max_w, "height": max_h},
        )

    issues = []

    if x < min_x:
        issues.append(f"x={x} < {min_x}")
    elif x > max_x:
        issues.append(f"x={x} > {max_x}")

    if y < min_y:
        issues.append(f"y={y} < {min_y}")
    elif y > max_y:
        issues.append(f"y={y} > {max_y}")

    if issues:
        # Clamp
        clamped = {
            "x": max(min_x, min(max_x, x)),
            "y": max(min_y, min(max_y, y)),
        }
        clamped["x"] = round(clamped["x"])
        clamped["y"] = round(clamped["y"])

        logger.debug(
            f"Coordinate ({x}, {y}) out of bounds ({space}), "
            f"clamped to ({clamped['x']}, {clamped['y']})"
        )

        return ValidationResult(
            valid=False,
            reason=f"Out of bounds ({space}): {'; '.join(issues)}",
            clamped=clamped,
            display={"width": max_w, "height": max_h},
        )

    return ValidationResult(
        valid=True,
        reason="Within bounds",
        display={"width": max_w, "height": max_h},
    )


def find_display_for_point(
    x: int,
    y: int,
    displays: Optional[list] = None,
) -> Optional[dict]:
    """Find which display contains a given pixel coordinate.

    Maps to OpenGuider's bounds-validator.js findDisplayForPoint().

    Args:
        x, y: Absolute pixel coordinates
        displays: List of display bounds dicts [{x, y, width, height, id}]

    Returns:
        Matching display dict or None
    """
    if not displays:
        return None

    for display in displays:
        dx = display.get("x", 0)
        dy = display.get("y", 0)
        dw = display.get("width", 0)
        dh = display.get("height", 0)

        if dx <= x < dx + dw and dy <= y < dy + dh:
            return display

    return None


# ── Normalize/denormalize (operates on pixel space) ───────────────────────────

def normalize_to_0_to_1000(
    x: int,
    y: int,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> dict:
    """Convert absolute pixel coords to 0-1000 normalized range.

    Maps to OpenGuider's bounds-validator.js normalizeTo0to1000().
    """
    if screen_width <= 0:
        screen_width = 1
    if screen_height <= 0:
        screen_height = 1

    return {
        "x": round((x / screen_width) * 1000, 1),
        "y": round((y / screen_height) * 1000, 1),
    }


def denormalize_from_0_to_1000(
    nx: float,
    ny: float,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> dict:
    """Convert 0-1000 normalized coords to absolute pixels.

    Maps to OpenGuider's bounds-validator.js denormalizeFrom0to1000().
    """
    if screen_width <= 0:
        screen_width = 1
    if screen_height <= 0:
        screen_height = 1

    return {
        "x": round((nx / 1000.0) * screen_width),
        "y": round((ny / 1000.0) * screen_height),
    }
