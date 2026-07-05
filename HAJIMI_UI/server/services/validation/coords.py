"""
HAJIMI_UI — Coordinate validation and normalization.

Mirrors OpenGuider's src/validation/bounds-validator.js.
Pure Python, zero dependencies.
"""
from __future__ import annotations


def normalize_coordinate(norm_x: float, norm_y: float, screen_w: int = 1920, screen_h: int = 1080) -> tuple[int, int]:
    """Convert 0-1000 normalized coordinates to absolute screen pixels.

    Args:
        norm_x: Normalized x (0-1000)
        norm_y: Normalized y (0-1000)
        screen_w: Screen width in pixels
        screen_h: Screen height in pixels

    Returns:
        (abs_x, abs_y) tuple of absolute pixel coordinates
    """
    abs_x = int(round((norm_x / 1000.0) * screen_w))
    abs_y = int(round((norm_y / 1000.0) * screen_h))
    return abs_x, abs_y


def clamp_to_bounds(x: int, y: int, screen_w: int = 1920, screen_h: int = 1080, margin: int = 10) -> tuple[int, int, bool]:
    """Clamp coordinates to screen bounds with margin.

    Args:
        x, y: Absolute pixel coordinates
        screen_w, screen_h: Screen dimensions
        margin: Minimum distance from screen edge

    Returns:
        (clamped_x, clamped_y, was_clamped)
    """
    clamped = False
    cx, cy = x, y

    if cx < margin:
        cx = margin
        clamped = True
    elif cx > screen_w - margin:
        cx = screen_w - margin
        clamped = True

    if cy < margin:
        cy = margin
        clamped = True
    elif cy > screen_h - margin:
        cy = screen_h - margin
        clamped = True

    return cx, cy, clamped


def validate_coordinate(x: int, y: int, screen_w: int = 1920, screen_h: int = 1080) -> tuple[int, int, bool]:
    """Validate and clamp a coordinate. Convenience wrapper.

    Returns:
        (validated_x, validated_y, is_valid)
    """
    cx, cy, clamped = clamp_to_bounds(x, y, screen_w, screen_h)
    return cx, cy, True
