"""Orange cat (耄耋) theme tokens — production."""
from __future__ import annotations

from dataclasses import dataclass

from ui.native.layout_tokens import RADIUS_COMPACT, SHELL_RADIUS as LAYOUT_SHELL_RADIUS

ORANGE_CAT_THEME_ID = "variant_orange_cat"
ORANGE_CAT_THEME_LABEL = "橘猫耄耋"

# Back-compat aliases for demo imports
THEME_ID = ORANGE_CAT_THEME_ID
THEME_LABEL = ORANGE_CAT_THEME_LABEL

PRIMARY = "#FFB366"
PRIMARY_DARK = "#E89540"
PRIMARY_RGB = (255, 179, 102)
BG_CREAM = "#FFF2E2"
BG_WARM = "#F7D4A8"
TEXT_PRIMARY = "#3A271B"
TEXT_MUTED = "#8B7360"
DIVIDER = "rgba(139, 115, 96, 0.1)"
ACCENT_PINK = "#F0A89A"
SHELL_GLASS = (255, 242, 226, 230)
SHELL_BORDER = (247, 212, 168, 180)

TOPBAR_STYLE_GLASS = "glass_orange"
TOPBAR_STYLE_HERO = "hero_gradient"
DEFAULT_TOPBAR_STYLE = TOPBAR_STYLE_GLASS
TOPBAR_HERO_FADE_RATIO = 0.25

SHELL_RADIUS = LAYOUT_SHELL_RADIUS
COMPACT_RADIUS = RADIUS_COMPACT

DEFAULT_SCALE_IN_MS = 400
DEFAULT_HOLD_MS = 800
DEFAULT_FADE_OUT_MS = 300
DEFAULT_IDLE_MINUTES = 0


@dataclass(frozen=True)
class OrangeCatTokens:
    primary: str = PRIMARY
    primary_dark: str = PRIMARY_DARK
    bg_cream: str = BG_CREAM
    bg_warm: str = BG_WARM
    text_primary: str = TEXT_PRIMARY
    text_muted: str = TEXT_MUTED
    divider: str = DIVIDER
    accent_pink: str = ACCENT_PINK


TOKENS = OrangeCatTokens()
