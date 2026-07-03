"""
Windows UI Automation scanner for desktop control element detection.

Python equivalent of OpenGuider's perception/ui-scanner.js.
Instead of PowerShell subprocess with UIAutomationClient COM,
we use pywin32 COM directly, falling back to comtypes → ctypes.

Returns up to 5000 interactive UI elements with name, controlType,
automationId, className, and bounding rectangle.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class UIAElement:
    """A single UI Automation element on screen."""
    name: str = ""
    control_type: str = ""
    automation_id: str = ""
    class_name: str = ""
    is_enabled: bool = True
    rect: dict = field(default_factory=lambda: {
        "x": 0, "y": 0, "width": 0, "height": 0,
        "x1": 0, "y1": 0,
    })
    element_id: str = ""  # Auto-generated: "uia_1", "uia_2", ...


@dataclass
class SnapResult:
    """Result of snapping a coordinate to nearest UI element."""
    element: UIAElement
    snapped_coordinate: Tuple[int, int]
    distance: float


# ── Implementation selection ──────────────────────────────────────────────────

_impl = None  # 'pywin32', 'comtypes', 'ctypes', or None


def _get_implementation():
    """Probe for the best available UIA implementation.

    Priority: PowerShell > pywin32 > comtypes > ctypes
    PowerShell is the most reliable (same approach as OpenGuider).
    """
    global _impl
    if _impl is not None:
        return _impl

    # Try PowerShell first (OpenGuider's approach — most reliable)
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Write-Host 'ok'"],
            capture_output=True, timeout=5, text=True,
        )
        if "ok" in (result.stdout or ""):
            _impl = "powershell"
            logger.info("UIA implementation: powershell")
            return _impl
    except Exception:
        pass

    # Try pywin32 next
    try:
        import win32com.client
        uia = win32com.client.Dispatch("UIAutomationClient.CUIAutomation")
        if uia:
            _impl = "pywin32"
            logger.info("UIA implementation: pywin32")
            return _impl
    except Exception:
        pass

    # Try comtypes
    try:
        import comtypes.client
        uia = comtypes.client.CreateObject("UIAutomationClient.CUIAutomation")
        if uia:
            _impl = "comtypes"
            logger.info("UIA implementation: comtypes")
            return _impl
    except Exception:
        pass

    # ctypes fallback (only gives window-level info, not controls)
    try:
        import ctypes
        _impl = "ctypes"
        logger.info("UIA implementation: ctypes (limited)")
        return _impl
    except Exception:
        pass

    _impl = None
    logger.warning("No UIA implementation available. UI scanning disabled.")
    return _impl


# ── PowerShell implementation (most reliable — matches OpenGuider) ──────────


def _query_uia_powershell(max_elements: int = 5000) -> List[dict]:
    """Query UIA via PowerShell — same approach as OpenGuider's ui-scanner.js.

    Writes a PS script to temp directory and executes it via subprocess.
    This is the most reliable method because PowerShell has built-in UIA support.
    """
    import subprocess
    import json
    import tempfile
    import os

    ps_script = r"""
Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
Add-Type -AssemblyName UIAutomationTypes -ErrorAction SilentlyContinue

$root = [System.Windows.Automation.AutomationElement]::RootElement
$isControl = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::IsControlElementProperty, $true
)
$notOffscreen = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::IsOffscreenProperty, $false
)
$isEnabled = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::IsEnabledProperty, $true
)
$condition = New-Object System.Windows.Automation.AndCondition($isControl, $notOffscreen, $isEnabled)

$elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)

$results = @()
$count = 0
""" + f"$maxElements = {max_elements}" + r"""

foreach ($el in $elements) {
  if ($count -ge $maxElements) { break }
  try {
    $name = $el.Current.Name
    $rect = $el.Current.BoundingRectangle
    if ([string]::IsNullOrWhiteSpace($name)) { continue }
    if ($rect.Width -le 0 -or $rect.Height -le 0) { continue }
    if ([double]::IsInfinity($rect.X) -or [double]::IsInfinity($rect.Y)) { continue }

    $safeName = $name -replace '[\x00-\x1F\x7F]', ''
    $safeAutoId = ($el.Current.AutomationId) -replace '[\x00-\x1F\x7F]', ''
    $safeClass = ($el.Current.ClassName) -replace '[\x00-\x1F\x7F]', ''
    $safeType = ($el.Current.LocalizedControlType) -replace '[\x00-\x1F\x7F]', ''

    $obj = @{
      name = $safeName
      controlType = $safeType
      automationId = $safeAutoId
      className = $safeClass
      isEnabled = $el.Current.IsEnabled
      rect = @{
        x = [int]$rect.X
        y = [int]$rect.Y
        width = [int]$rect.Width
        height = [int]$rect.Height
        x1 = [int]($rect.X + $rect.Width)
        y1 = [int]($rect.Y + $rect.Height)
      }
    }
    $results += $obj
    $count++
  } catch { }
}

$results | ConvertTo-Json -Depth 3 -Compress
"""

    try:
        # Write script to temp file
        script_path = os.path.join(tempfile.gettempdir(), "hajimi_uia_query.ps1")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(ps_script)

        # Execute
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", script_path,
            ],
            capture_output=True,
            timeout=25,
            text=True,
        )

        stdout = (result.stdout or "").strip()
        if not stdout or stdout == "null" or stdout == "":
            return []

        # Strip control characters
        import re
        stdout = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", stdout)

        parsed = json.loads(stdout)
        elements = parsed if isinstance(parsed, list) else [parsed]
        return [e for e in elements if e.get("name") and e.get("rect")]

    except subprocess.TimeoutExpired:
        logger.warning("PowerShell UIA query timed out")
        return []
    except json.JSONDecodeError as e:
        logger.warning(f"PowerShell UIA JSON parse error: {e}")
        return []
    except FileNotFoundError:
        logger.warning("PowerShell not found — UIA via PS unavailable")
        return []
    except Exception as e:
        logger.warning(f"PowerShell UIA query failed: {e}")
        return []


# ── ctypes fallback (limited - no UIA tree) ───────────────────────────────────


def _query_uia_ctypes(max_elements: int = 5000) -> List[dict]:
    """Minimal fallback using ctypes - enumerates windows only, not controls.
    Returns empty list; use window_enum.py for window-level info instead.
    """
    logger.warning("UIA via ctypes: full UI element tree not available. Returning empty list.")
    return []


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sanitize(s: str) -> str:
    """Strip control characters that break JSON."""
    if not s:
        return ""
    return "".join(ch for ch in s if ord(ch) >= 32 and ord(ch) != 127)


# ── Public API ────────────────────────────────────────────────────────────────


def query_ui_automation(max_elements: int = 5000) -> List[UIAElement]:
    """Query all interactive UI elements on the desktop.

    Maps to OpenGuider's ui-scanner.js queryUIAutomation().

    Args:
        max_elements: Maximum elements to return (default 5000)

    Returns:
        List of UIAElement dataclass instances with name, rect, etc.
    """
    impl = _get_implementation()
    if impl is None:
        logger.warning("No UIA implementation available")
        return []

    try:
        if impl == "powershell":
            raw = _query_uia_powershell(max_elements)
        elif impl == "pywin32":
            raw = _query_uia_pywin32(max_elements)
        elif impl == "comtypes":
            raw = _query_uia_comtypes(max_elements)
        elif impl == "ctypes":
            raw = _query_uia_ctypes(max_elements)
        else:
            raw = []
    except Exception as e:
        logger.error(f"UIA query failed ({impl}): {e}")
        raw = []

    # Convert to UIAElement dataclasses
    elements = []
    for i, item in enumerate(raw):
        elements.append(UIAElement(
            name=item.get("name", ""),
            control_type=item.get("controlType", ""),
            automation_id=item.get("automationId", ""),
            class_name=item.get("className", ""),
            is_enabled=item.get("isEnabled", True),
            rect=item.get("rect", {"x": 0, "y": 0, "width": 0, "height": 0, "x1": 0, "y1": 0}),
            element_id=f"uia_{i + 1}",
        ))

    logger.info(f"Found {len(elements)} UI elements via {impl}")
    return elements


def calculate_element_center(rect: dict) -> Optional[Tuple[int, int]]:
    """Calculate geometric center of a bounding rectangle.

    Maps to OpenGuider's ui-scanner.js calculateElementCenter().
    """
    if not rect:
        return None
    return (
        round(rect.get("x", 0) + rect.get("width", 0) / 2),
        round(rect.get("y", 0) + rect.get("height", 0) / 2),
    )


def is_within_bounds(
    coordinate: Tuple[int, int],
    rect: dict,
    tolerance: int = 50,
) -> bool:
    """Check if a coordinate falls within (or near) a bounding rectangle.

    Maps to OpenGuider's ui-scanner.js isWithinBounds().
    """
    if not coordinate or not rect:
        return False
    x, y = coordinate
    x1 = rect.get("x1", rect.get("x", 0) + rect.get("width", 0))
    y1 = rect.get("y1", rect.get("y", 0) + rect.get("height", 0))
    return (
        x >= rect.get("x", 0) - tolerance
        and x <= x1 + tolerance
        and y >= rect.get("y", 0) - tolerance
        and y <= y1 + tolerance
    )


def snap_to_nearest_element(
    coordinate: Tuple[int, int],
    elements: List[UIAElement],
    tolerance: int = 50,
) -> Optional[SnapResult]:
    """Find the nearest UI element center to a coordinate.

    Maps to OpenGuider's ui-scanner.js snapToNearestElement().

    Args:
        coordinate: (x, y) pixel coordinate to snap
        elements: UIAElement list to search
        tolerance: Max distance in pixels for a valid snap

    Returns:
        SnapResult with element, snapped_coordinate, and distance; or None
    """
    if not coordinate or not elements:
        return None

    nearest = None
    nearest_dist = float("inf")

    cx, cy = coordinate

    for element in elements:
        center = calculate_element_center(element.rect)
        if not center:
            continue
        ex, ey = center
        dx = cx - ex
        dy = cy - ey
        dist = (dx * dx + dy * dy) ** 0.5

        if dist < nearest_dist and dist <= tolerance:
            nearest_dist = dist
            nearest = SnapResult(
                element=element,
                snapped_coordinate=center,
                distance=dist,
            )

    if nearest:
        logger.debug(
            f"Snapped to element '{nearest.element.name}' "
            f"at ({nearest.snapped_coordinate[0]}, {nearest.snapped_coordinate[1]}), "
            f"distance={nearest.distance:.1f}px"
        )

    return nearest


def find_matching_elements(
    target_label: str,
    elements: List[UIAElement],
    fuzzy: bool = True,
) -> List[UIAElement]:
    """Find UI elements matching a target label string.

    Maps to OpenGuider's ui-scanner.js findMatchingElements().

    Uses fuzzy substring matching by default:
    - Checks if target_label is substring of element name/controlType/automationId
    - Also checks reverse if element name is >= 4 chars (safer)

    Args:
        target_label: Text label to search for
        elements: UIAElement list to search
        fuzzy: Use fuzzy substring matching (default True)

    Returns:
        List of matching UIAElement instances
    """
    if not target_label or not elements:
        return []

    lower_target = target_label.lower()
    matches = []

    for element in elements:
        name = (element.name or "").lower()
        control_type = (element.control_type or "").lower()
        auto_id = (element.automation_id or "").lower()

        if fuzzy:
            # Substring matching: target in element fields
            matches_substring = (
                lower_target in name
                or lower_target in control_type
                or lower_target in auto_id
            )
            # Reverse: element name in target (only if name is meaningful)
            matches_reversed = (
                len(name) >= 4 and name in lower_target
            )

            if matches_substring or matches_reversed:
                matches.append(element)
        else:
            if (
                name == lower_target
                or control_type == lower_target
            ):
                matches.append(element)

    return matches
