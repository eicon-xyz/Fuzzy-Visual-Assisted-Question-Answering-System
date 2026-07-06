"""Orange cat mood palettes — production defaults to fresh."""
from __future__ import annotations

from dataclasses import dataclass

MOOD_WARM = "warm"
MOOD_FRESH = "fresh"
MOOD_VIVID = "vivid"
DEFAULT_MOOD = MOOD_FRESH
PRODUCTION_MOOD = MOOD_FRESH

PRIMARY = "#FFB366"
PRIMARY_DARK = "#E89540"
ACCENT_PINK = "#F0A89A"


@dataclass(frozen=True)
class MaodiaoPalette:
    mood_id: str
    label: str
    shell_glass: tuple[int, int, int, int]
    shell_border: tuple[int, int, int, int]
    topbar_glass_fill: tuple[int, int, int, int]
    topbar_hero_top: tuple[int, int, int]
    topbar_hero_mid: tuple[int, int, int]
    topbar_hero_end: tuple[int, int, int, int]
    bg_cream: str
    bg_warm: str
    text_primary: str
    text_muted: str
    divider: str
    accent_secondary: str
    primary: str
    primary_dark: str
    bubble_user_bg: str
    bubble_user_border: str
    bubble_system_bg: str
    bubble_system_border: str
    bubble_system_border_left: str
    input_bg: str
    input_dock_bg: str
    input_border: str
    input_focus_border: str
    primary_soft: str
    primary_hover: str
    menu_hover: str
    send_btn_css: str
    send_btn_hover_css: str
    status_idle_bg: str
    status_idle_color: str
    status_idle_border: str
    status_processing_bg: str
    status_processing_color: str
    status_processing_border: str
    bubble_radius: int
    input_radius: int
    top_sub_color: str
    drawer_bg: str


def _warm() -> MaodiaoPalette:
    return MaodiaoPalette(
        mood_id=MOOD_WARM,
        label="暖奶油（原版）",
        shell_glass=(255, 242, 226, 230),
        shell_border=(247, 212, 168, 180),
        topbar_glass_fill=(255, 225, 195, 248),
        topbar_hero_top=(255, 179, 102),
        topbar_hero_mid=(245, 200, 150),
        topbar_hero_end=(255, 242, 226, 230),
        bg_cream="#FFF2E2",
        bg_warm="#F7D4A8",
        text_primary="#3A271B",
        text_muted="#8B7360",
        divider="rgba(139, 115, 96, 0.1)",
        accent_secondary=ACCENT_PINK,
        primary=PRIMARY,
        primary_dark=PRIMARY_DARK,
        bubble_user_bg="#FFF2E2",
        bubble_user_border="rgba(139, 115, 96, 0.1)",
        bubble_system_bg="rgba(255, 242, 226, 0.85)",
        bubble_system_border="rgba(139, 115, 96, 0.1)",
        bubble_system_border_left="none",
        input_bg="rgba(255, 242, 226, 230)",
        input_dock_bg="rgba(255, 242, 226, 230)",
        input_border="rgba(139, 115, 96, 0.1)",
        input_focus_border="rgba(255, 179, 102, 0.35)",
        primary_soft="rgba(255, 179, 102, 0.15)",
        primary_hover="rgba(255, 179, 102, 0.10)",
        menu_hover="rgba(255, 179, 102, 0.10)",
        send_btn_css="background: transparent; border: none; color: #3A271B;",
        send_btn_hover_css="background: rgba(255, 179, 102, 0.10);",
        status_idle_bg="#FFF2E2",
        status_idle_color="#8B7360",
        status_idle_border="rgba(139, 115, 96, 0.1)",
        status_processing_bg="rgba(255, 179, 102, 0.15)",
        status_processing_color="#E89540",
        status_processing_border="rgba(255, 179, 102, 0.25)",
        bubble_radius=10,
        input_radius=10,
        top_sub_color="#E89540",
        drawer_bg="#FFF2E2",
    )


def _fresh() -> MaodiaoPalette:
    return MaodiaoPalette(
        mood_id=MOOD_FRESH,
        label="清新近白",
        shell_glass=(255, 251, 247, 235),
        shell_border=(232, 149, 64, 220),
        topbar_glass_fill=(255, 232, 205, 252),
        topbar_hero_top=(255, 185, 115),
        topbar_hero_mid=(255, 210, 170),
        topbar_hero_end=(255, 253, 250, 230),
        bg_cream="#FFFBF7",
        bg_warm="#F5EBE0",
        text_primary="#3A2718",
        text_muted="#7A6E62",
        divider="rgba(122, 110, 98, 0.16)",
        accent_secondary=PRIMARY,
        primary=PRIMARY,
        primary_dark=PRIMARY_DARK,
        bubble_user_bg="#FFFFFF",
        bubble_user_border="rgba(122, 110, 98, 0.22)",
        bubble_system_bg="#FFF5EB",
        bubble_system_border="rgba(122, 110, 98, 0.18)",
        bubble_system_border_left=f"3px solid {PRIMARY}",
        input_bg="rgba(255, 255, 255, 240)",
        input_dock_bg="rgba(255, 251, 247, 230)",
        input_border="rgba(122, 110, 98, 0.22)",
        input_focus_border="rgba(255, 179, 102, 0.55)",
        primary_soft="rgba(255, 179, 102, 0.14)",
        primary_hover="rgba(255, 179, 102, 0.16)",
        menu_hover="rgba(255, 179, 102, 0.24)",
        send_btn_css="background: transparent; border: none; color: #3A2718;",
        send_btn_hover_css="background: rgba(255, 179, 102, 0.20);",
        status_idle_bg="#FFFFFF",
        status_idle_color="#52B788",
        status_idle_border="rgba(82, 183, 136, 0.28)",
        status_processing_bg="rgba(255, 179, 102, 0.18)",
        status_processing_color="#E89540",
        status_processing_border="rgba(232, 149, 64, 0.35)",
        bubble_radius=12,
        input_radius=14,
        top_sub_color="#E89540",
        drawer_bg="#FFFBF7",
    )


def _vivid() -> MaodiaoPalette:
    return MaodiaoPalette(
        mood_id=MOOD_VIVID,
        label="高饱和活力",
        shell_glass=(255, 248, 240, 230),
        shell_border=(255, 200, 140, 190),
        topbar_glass_fill=(255, 215, 175, 252),
        topbar_hero_top=(255, 160, 70),
        topbar_hero_mid=(255, 190, 120),
        topbar_hero_end=(255, 242, 226, 230),
        bg_cream="#FFF8F0",
        bg_warm="#FFD9A8",
        text_primary="#3A271B",
        text_muted="#8B7360",
        divider="rgba(232, 149, 64, 0.18)",
        accent_secondary=ACCENT_PINK,
        primary=PRIMARY,
        primary_dark=PRIMARY_DARK,
        bubble_user_bg="#FFFFFF",
        bubble_user_border="rgba(232, 149, 64, 0.35)",
        bubble_system_bg="rgba(255, 235, 210, 0.92)",
        bubble_system_border="rgba(232, 149, 64, 0.22)",
        bubble_system_border_left=f"3px solid {PRIMARY_DARK}",
        input_bg="rgba(255, 255, 255, 230)",
        input_dock_bg="rgba(255, 248, 240, 230)",
        input_border="rgba(232, 149, 64, 0.22)",
        input_focus_border="rgba(255, 179, 102, 0.55)",
        primary_soft="rgba(255, 179, 102, 0.22)",
        primary_hover="rgba(255, 179, 102, 0.18)",
        menu_hover="rgba(255, 179, 102, 0.18)",
        send_btn_css=(
            "background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:1, "
            "stop:0 #FFB366, stop:1 #E89540);"
            " border: none; color: #FFFFFF;"
        ),
        send_btn_hover_css=(
            "background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:1, "
            "stop:0 #FFC480, stop:1 #F0A040);"
        ),
        status_idle_bg="rgba(255, 179, 102, 0.28)",
        status_idle_color="#FFFFFF",
        status_idle_border="rgba(232, 149, 64, 0.45)",
        status_processing_bg="rgba(240, 168, 154, 0.35)",
        status_processing_color="#C45A4A",
        status_processing_border="rgba(240, 168, 154, 0.45)",
        bubble_radius=10,
        input_radius=10,
        top_sub_color="#E89540",
        drawer_bg="#FFF8F0",
    )


PALETTES: dict[str, MaodiaoPalette] = {
    MOOD_WARM: _warm(),
    MOOD_FRESH: _fresh(),
    MOOD_VIVID: _vivid(),
}


def get_palette(mood_id: str | None) -> MaodiaoPalette:
    key = (mood_id or "").strip() or DEFAULT_MOOD
    return PALETTES.get(key, PALETTES[DEFAULT_MOOD])


def production_palette() -> MaodiaoPalette:
    return get_palette(PRODUCTION_MOOD)
