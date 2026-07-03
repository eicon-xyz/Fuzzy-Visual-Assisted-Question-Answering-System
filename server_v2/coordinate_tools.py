"""
Coordinate normalization tools for screen-aware guidance.

Converts between absolute pixel coordinates and the 0-1000 normalized
coordinate system used by LLMs. Maps to OpenGuider's pointer-tool.js +
bounds-validator.js normalization functions.

The 0-1000 range is chosen because:
- LLMs are bad at precise pixel coordinates but good at proportions
- 0-1000 gives enough granularity without being unwieldy
- Single-monitor: (500, 500) = center, (0, 0) = top-left
- Multi-monitor: :screenN suffix disambiguates displays
"""

import ctypes
import math
from dataclasses import dataclass, field
from typing import Optional, Tuple


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class NormalizedPoint:
    """Coordinate in 0-1000 range relative to a display."""
    x: float
    y: float
    screen_number: int = 1

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass
class PixelPoint:
    """Absolute pixel coordinate on screen."""
    x: int
    y: int

    def to_tuple(self) -> Tuple[int, int]:
        return (self.x, self.y)


@dataclass
class DisplayBounds:
    """Physical bounds of a display."""
    x: int = 0
    y: int = 0
    width: int = 1920
    height: int = 1080
    display_id: str = "primary"

    @property
    def center(self) -> PixelPoint:
        return PixelPoint(
            x=math.floor(self.x + self.width / 2),
            y=math.floor(self.y + self.height / 2),
        )


# ── Display enumeration ───────────────────────────────────────────────────────


def get_primary_display_bounds() -> DisplayBounds:
    """Get primary display bounds via ctypes Win32 API.
    Falls back to 1920x1080 if unavailable.
    """
    try:
        user32 = ctypes.windll.user32
        width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
        height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        if width > 0 and height > 0:
            return DisplayBounds(x=0, y=0, width=width, height=height, display_id="primary")
    except Exception:
        pass
    return DisplayBounds()  # fallback


def get_all_display_bounds() -> list:
    """Get all display bounds via EnumDisplayMonitors.
    Falls back to primary display if unavailable.
    """
    displays = []
    try:
        user32 = ctypes.windll.user32

        # Define MONITORENUMPROC callback
        monitors = []

        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.wintypes.RECT),
            ctypes.c_void_p,
        )

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        def callback(hMonitor, hdc, lprcMonitor, dwData):
            rect = lprcMonitor.contents
            monitors.append({
                "x": rect.left,
                "y": rect.top,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
            })
            return 1

        cb = MONITORENUMPROC(callback)
        user32.EnumDisplayMonitors(None, None, cb, 0)

        for i, m in enumerate(monitors):
            displays.append(DisplayBounds(
                x=m["x"], y=m["y"],
                width=m["width"], height=m["height"],
                display_id=f"display_{i}" if i > 0 else "primary",
            ))
    except Exception:
        pass

    if not displays:
        displays.append(get_primary_display_bounds())
    return displays


# ── Normalization ──────────────────────────────────────────────────────────────


def normalize_to_0_1000(
    x: float, y: float,
    screen_width: int,
    screen_height: int,
) -> NormalizedPoint:
    """Convert absolute pixel coords to 0-1000 normalized range.

    LLMs receive coordinates in 0-1000 space and return them the same way.
    This is the encoding step (pixel -> normalized).
    """
    if screen_width <= 0:
        screen_width = 1
    if screen_height <= 0:
        screen_height = 1

    return NormalizedPoint(
        x=round((x / screen_width) * 1000, 1),
        y=round((y / screen_height) * 1000, 1),
    )


def denormalize_from_0_1000(
    nx: float, ny: float,
    screen_width: int,
    screen_height: int,
) -> PixelPoint:
    """Convert 0-1000 normalized coords back to absolute pixels.
    This is the decoding step (normalized -> pixel).
    """
    if screen_width <= 0:
        screen_width = 1
    if screen_height <= 0:
        screen_height = 1

    return PixelPoint(
        x=round((nx / 1000.0) * screen_width),
        y=round((ny / 1000.0) * screen_height),
    )


def resolve_normalized_coordinate(
    coordinate: Optional[dict],
    display_bounds: DisplayBounds,
    calibration: Optional[dict] = None,
) -> Optional[PixelPoint]:
    """Resolve a normalized LLM coordinate to absolute screen position.

    Handles three input formats (maps to OpenGuider's normalizeCoordinate):
    - 0-1 fraction: (0.5, 0.5) -> center
    - 0-1000 range: (500, 500) -> center
    - Raw pixels: passed through with scale calibration

    Args:
        coordinate: dict with 'x' and 'y' keys (from LLM)
        display_bounds: target display bounds
        calibration: optional {sourceWidth, sourceHeight, scaleX, scaleY}

    Returns:
        PixelPoint with absolute screen coordinates, or None
    """
    if not coordinate:
        return None

    source_width = max(1, calibration.get("sourceWidth", display_bounds.width) if calibration else display_bounds.width)
    source_height = max(1, calibration.get("sourceHeight", display_bounds.height) if calibration else display_bounds.height)

    scale_x = calibration.get("scaleX", display_bounds.width / source_width) if calibration else (display_bounds.width / source_width)
    scale_y = calibration.get("scaleY", display_bounds.height / source_height) if calibration else (display_bounds.height / source_height)

    if not (isinstance(scale_x, (int, float)) and scale_x > 0):
        scale_x = 1.0
    if not (isinstance(scale_y, (int, float)) and scale_y > 0):
        scale_y = 1.0

    x = coordinate.get("x", 0)
    y = coordinate.get("y", 0)

    # Detect: 0-1 fractional range
    if 0 < x <= 1 and 0 < y <= 1:
        x = round(x * source_width)
        y = round(y * source_height)
    # Detect: 0-1000 normalized range
    elif 1 < x <= 1000 and 1 < y <= 1000:
        x = round((x / 1000.0) * source_width)
        y = round((y / 1000.0) * source_height)
    # Else: assume raw pixels

    return PixelPoint(
        x=round(display_bounds.x + (x * scale_x)),
        y=round(display_bounds.y + (y * scale_y)),
    )


# ── Clamping ──────────────────────────────────────────────────────────────────


def clamp_to_bounds(
    point: NormalizedPoint,
    bounds: Optional[DisplayBounds] = None,
    margin: int = 5,
) -> NormalizedPoint:
    """Clamp a 0-1000 normalized coordinate to valid screen area.
    Returns the clamped point (0 to 1000 range).
    """
    return NormalizedPoint(
        x=max(0.0 + margin, min(1000.0 - margin, point.x)),
        y=max(0.0 + margin, min(1000.0 - margin, point.y)),
        screen_number=point.screen_number,
    )


def validate_bounds(
    point: NormalizedPoint,
    bounds: Optional[DisplayBounds] = None,
) -> dict:
    """Check if normalized coordinate is within valid bounds.
    Returns: {valid: bool, reason: str, clamped: NormalizedPoint | None}
    """
    reasons = []
    if point.x < 0:
        reasons.append("x < 0")
    if point.x > 1000:
        reasons.append("x > 1000")
    if point.y < 0:
        reasons.append("y < 0")
    if point.y > 1000:
        reasons.append("y > 1000")

    if reasons:
        clamped = clamp_to_bounds(point, bounds)
        return {"valid": False, "reason": f"Out of bounds: {', '.join(reasons)}", "clamped": clamped}

    return {"valid": True, "reason": "within bounds", "clamped": None}


# ── Convenience helpers ────────────────────────────────────────────────────────


def center_point() -> NormalizedPoint:
    """Return the center of the screen in normalized coords (500, 500)."""
    return NormalizedPoint(x=500.0, y=500.0)


def distance(a: NormalizedPoint, b: NormalizedPoint) -> float:
    """Euclidean distance between two normalized points."""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)
