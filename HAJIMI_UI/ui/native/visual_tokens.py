"""Visual tokens — colors for Python painting / overlay (non-QSS)."""

# Colors (--bg-primary, --accent, etc.)
BG_PRIMARY = "#0f172a"
BG_SECONDARY = "#1e293b"
GLASS_FILL = "rgba(15, 23, 42, 0.89)"
GLASS_BORDER = "rgba(255, 255, 255, 0.12)"
SURFACE_FILL = "rgba(30, 41, 59, 0.55)"
SURFACE_BORDER = "rgba(255, 255, 255, 0.08)"
TEXT_PRIMARY = "#f1f5f9"
TEXT_SECONDARY = "#94a3b8"
TEXT_TERTIARY = "#64748b"
ACCENT = "#7c8fd4"
ACCENT_SOFT = "rgba(124, 143, 212, 0.15)"
ACCENT_HOVER = "#8fa0dc"

THEME_ACCENTS: dict[str, str] = {
    "current": "#7c8fd4",
    "variant_b": "#6b8cce",
    "variant_c": "#5ab89e",
}


def accent_for_theme(theme_id: str) -> str:
    return THEME_ACCENTS.get(theme_id, THEME_ACCENTS["current"])
DANGER = "#e74c3c"
DANGER_SOFT = "rgba(231, 76, 60, 0.15)"
SUCCESS = "#2ecc71"
WARNING = "#f1c40f"
INSPECT = "#38bdf8"
INSPECT_BORDER = "rgba(56, 189, 248, 0.45)"
PREPARE_BORDER = INSPECT_BORDER
SUSPENSION_BORDER = "rgba(241, 196, 15, 0.4)"

# Overlay (aligned with HTML --danger for task highlight)
OVERLAY_HIGHLIGHT = DANGER
OVERLAY_HIGHLIGHT_RGB = (231, 76, 60)
OVERLAY_INSPECT_RGB = (0, 200, 255)
OVERLAY_ARROW_RGB = (0, 122, 255)

# Scrollbar (Q14-A: nearly invisible until hover)
SCROLLBAR_HANDLE = "rgba(255, 255, 255, 0.08)"
SCROLLBAR_HANDLE_HOVER = "rgba(255, 255, 255, 0.18)"

# Crystal shell shadow profile (Q13-B finalized)
CRYSTAL_SHADOW_DEFAULT = "light"
