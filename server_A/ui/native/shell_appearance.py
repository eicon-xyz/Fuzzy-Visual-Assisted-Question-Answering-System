"""Shell appearance tokens — shared by production ThemeManager and style demo."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect, QWidget

from ui.native.crystal_glass import GLASS_FILL_ALPHA
from ui.native.shell_paint import (
    DEFAULT_LIGHT_MODE,
    DEFAULT_QSS_BODY,
    DEFAULT_QSS_HIGHLIGHT,
    DEFAULT_QSS_HIGHLIGHT_PEAK,
    DEFAULT_TOP_LIGHT_PEAK,
    LIGHT_MODE_IDS,
    QSS_BODY_MODE_IDS,
    QSS_HIGHLIGHT_MODE_IDS,
)
from ui.native.luxury.qss import DEFAULT_LUXURY_BTN_MODE, DEFAULT_LUXURY_GOLD_MODE, LUXURY_BG_MODES
from ui.native.luxury.title import DEFAULT_SCRIPT_FONT_ID, LUXURY_SCRIPT_FONT_IDS
from ui.native.title_art import DEFAULT_TITLE_ART, TITLE_ART_MODE_IDS

LUXURY_THEME_ID = "variant_luxury"
LUXURY_BG_MODE_IDS = tuple(LUXURY_BG_MODES.keys())
DEFAULT_LUXURY_BG_MODE = "frosted"
DEFAULT_LUXURY_STAR_INTENSITY = 0
LUXURY_STAR_INTENSITY_MAX = 100

SHELL_STYLES: dict[str, str] = {
    "qss": "QSS 实底",
    "crystal_edge": "Crystal · 纯细边",
    "crystal_light": "Crystal · 极轻阴影",
}

SHELL_STYLE_IDS = tuple(SHELL_STYLES.keys())

DEFAULT_SHELL_STYLE = "qss"
DEFAULT_SHELL_ALPHA_MEDIUM = 89
DEFAULT_SHELL_ALPHA_COMPACT = 89
DEFAULT_FONT_SIZE = 13
DEFAULT_CRYSTAL_EDGE_SHADOW = 0
DEFAULT_CRYSTAL_LIGHT_SHADOW = 14
SHADOW_STRENGTH_MAX = 60

SHELL_ALPHA_MIN = 80
SHELL_ALPHA_MAX = 95
FONT_SIZE_MIN = 11
FONT_SIZE_MAX = 15

QSS_ALPHA_REF = 89
SHELL_BASE_RGB = (15, 23, 42)

_FONT_OVERRIDE_SELECTORS = (
    "QLabel",
    "QLabel#TopSub",
    "QWidget#TitleArt",
    "QLabel#CompactMark",
    "QLabel#CompactHint",
    "QLabel#HintText",
    "QLabel#HintTextSmall",
    "QLabel#SectionTitle",
    "QLabel#CardTitle",
    "QLabel#StatusBadge",
    "QPushButton#StepBtn",
    "QPushButton#StepBtnPrimary",
    "QLineEdit",
    "QLineEdit#CompactInput",
    "QLineEdit#SettingsInput",
    "QTextEdit",
    "QRadioButton#SettingsRadio",
)

_NAV_PINNED_FONT_RULE = (
    "QPushButton#MenuBtn, QPushButton#NavItem, QPushButton#NavItemQuit "
    "{ font-size: 12px !important; }"
)


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def is_luxury_theme(theme_id: str) -> bool:
    return str(theme_id) == LUXURY_THEME_ID


def is_crystal_shell(shell_style: str) -> bool:
    return str(shell_style).startswith("crystal")


def shell_renderer_mode(shell_style: str) -> str:
    return "crystal" if is_crystal_shell(shell_style) else "qss"


def default_crystal_shadow_strength(shell_style: str) -> int:
    if shell_style == "crystal_light":
        return DEFAULT_CRYSTAL_LIGHT_SHADOW
    if shell_style == "crystal_edge":
        return DEFAULT_CRYSTAL_EDGE_SHADOW
    return 0


def crystal_fill_alpha_from_percent(alpha_percent: int) -> int:
    pct = _clamp_int(alpha_percent, SHELL_ALPHA_MIN, SHELL_ALPHA_MAX)
    return max(1, min(255, int(GLASS_FILL_ALPHA * pct / QSS_ALPHA_REF)))


def qss_alpha_float(alpha_percent: int) -> float:
    return _clamp_int(alpha_percent, SHELL_ALPHA_MIN, SHELL_ALPHA_MAX) / 100.0


def qss_rgba_from_percent(alpha_percent: int) -> tuple[int, int, int, int]:
    r, g, b = SHELL_BASE_RGB
    a = int(round(qss_alpha_float(alpha_percent) * 255))
    return r, g, b, a


def _lerp_float(lo: float, hi: float, t: float) -> float:
    t = max(0.0, min(1.0, t))
    return lo + (hi - lo) * t


def shadow_params(strength: int) -> tuple[float, float, int]:
    t = max(0, min(SHADOW_STRENGTH_MAX, strength)) / float(SHADOW_STRENGTH_MAX)
    blur = _lerp_float(8.0, 32.0, t)
    offset_y = _lerp_float(2.0, 8.0, t)
    alpha = int(round(_lerp_float(16.0, 80.0, t)))
    return blur, offset_y, alpha


def apply_crystal_drop_shadow(widget: QWidget, strength: int) -> None:
    """Crystal outer shadow via DropShadow (strength 0–60)."""
    if strength <= 0:
        widget.setGraphicsEffect(None)
        return
    blur, offset_y, alpha = shadow_params(strength)
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, offset_y)
    fx.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(fx)


@dataclass(frozen=True)
class AppearanceSettings:
    shell_style: str = DEFAULT_SHELL_STYLE
    shell_alpha_medium: int = DEFAULT_SHELL_ALPHA_MEDIUM
    shell_alpha_compact: int = DEFAULT_SHELL_ALPHA_COMPACT
    font_size: int = DEFAULT_FONT_SIZE
    crystal_shadow_strength: int = DEFAULT_CRYSTAL_EDGE_SHADOW
    title_art_mode: str = DEFAULT_TITLE_ART
    top_light_mode: str = DEFAULT_LIGHT_MODE
    top_light_peak: int = DEFAULT_TOP_LIGHT_PEAK
    qss_body_mode: str = DEFAULT_QSS_BODY
    qss_highlight_mode: str = DEFAULT_QSS_HIGHLIGHT
    qss_highlight_peak: int = DEFAULT_QSS_HIGHLIGHT_PEAK
    luxury_bg_mode: str = DEFAULT_LUXURY_BG_MODE
    luxury_star_intensity: int = DEFAULT_LUXURY_STAR_INTENSITY
    luxury_script_font_id: str = DEFAULT_SCRIPT_FONT_ID
    luxury_gold_mode: str = DEFAULT_LUXURY_GOLD_MODE
    luxury_btn_mode: str = DEFAULT_LUXURY_BTN_MODE

    @classmethod
    def from_user_settings(cls, data: dict) -> AppearanceSettings:
        shell_style = data.get("shell_style", DEFAULT_SHELL_STYLE)
        if shell_style not in SHELL_STYLE_IDS:
            shell_style = DEFAULT_SHELL_STYLE
        shadow = data.get("crystal_shadow_strength")
        if shadow is None:
            shadow = default_crystal_shadow_strength(shell_style)
        title_art = data.get("title_art_mode", DEFAULT_TITLE_ART)
        if title_art == "glass":
            title_art = DEFAULT_TITLE_ART
        if title_art not in TITLE_ART_MODE_IDS:
            title_art = DEFAULT_TITLE_ART
        top_light_mode = data.get("top_light_mode", DEFAULT_LIGHT_MODE)
        if top_light_mode not in LIGHT_MODE_IDS:
            top_light_mode = DEFAULT_LIGHT_MODE
        qss_body = data.get("qss_body_mode", DEFAULT_QSS_BODY)
        if qss_body not in QSS_BODY_MODE_IDS:
            qss_body = DEFAULT_QSS_BODY
        qss_highlight = data.get("qss_highlight_mode", DEFAULT_QSS_HIGHLIGHT)
        if qss_highlight not in QSS_HIGHLIGHT_MODE_IDS:
            qss_highlight = DEFAULT_QSS_HIGHLIGHT
        luxury_bg = data.get("luxury_bg_mode", DEFAULT_LUXURY_BG_MODE)
        if luxury_bg not in LUXURY_BG_MODE_IDS:
            luxury_bg = DEFAULT_LUXURY_BG_MODE
        luxury_font = data.get("luxury_script_font_id", DEFAULT_SCRIPT_FONT_ID)
        if luxury_font not in LUXURY_SCRIPT_FONT_IDS:
            luxury_font = DEFAULT_SCRIPT_FONT_ID
        luxury_gold = data.get("luxury_gold_mode", DEFAULT_LUXURY_GOLD_MODE)
        if luxury_gold not in ("horizontal", "diagonal", "dual_layer"):
            luxury_gold = DEFAULT_LUXURY_GOLD_MODE
        luxury_btn = data.get("luxury_btn_mode", DEFAULT_LUXURY_BTN_MODE)
        if luxury_btn not in ("edge", "hover"):
            luxury_btn = DEFAULT_LUXURY_BTN_MODE
        return cls(
            shell_style=shell_style,
            shell_alpha_medium=_clamp_int(
                data.get("shell_alpha_medium", DEFAULT_SHELL_ALPHA_MEDIUM),
                SHELL_ALPHA_MIN,
                SHELL_ALPHA_MAX,
            ),
            shell_alpha_compact=_clamp_int(
                data.get("shell_alpha_compact", DEFAULT_SHELL_ALPHA_COMPACT),
                SHELL_ALPHA_MIN,
                SHELL_ALPHA_MAX,
            ),
            font_size=_clamp_int(
                data.get("font_size", DEFAULT_FONT_SIZE),
                FONT_SIZE_MIN,
                FONT_SIZE_MAX,
            ),
            crystal_shadow_strength=_clamp_int(
                shadow, 0, SHADOW_STRENGTH_MAX
            ),
            title_art_mode=title_art,
            top_light_mode=top_light_mode,
            top_light_peak=_clamp_int(
                data.get("top_light_peak", DEFAULT_TOP_LIGHT_PEAK),
                0,
                SHADOW_STRENGTH_MAX,
            ),
            qss_body_mode=qss_body,
            qss_highlight_mode=qss_highlight,
            qss_highlight_peak=_clamp_int(
                data.get("qss_highlight_peak", DEFAULT_QSS_HIGHLIGHT_PEAK),
                0,
                SHADOW_STRENGTH_MAX,
            ),
            luxury_bg_mode=luxury_bg,
            luxury_star_intensity=_clamp_int(
                data.get("luxury_star_intensity", DEFAULT_LUXURY_STAR_INTENSITY),
                0,
                LUXURY_STAR_INTENSITY_MAX,
            ),
            luxury_script_font_id=luxury_font,
            luxury_gold_mode=luxury_gold,
            luxury_btn_mode=luxury_btn,
        )

    def to_user_settings_fragment(self) -> dict:
        return {
            "shell_style": self.shell_style,
            "shell_alpha_medium": self.shell_alpha_medium,
            "shell_alpha_compact": self.shell_alpha_compact,
            "font_size": self.font_size,
            "crystal_shadow_strength": self.crystal_shadow_strength,
            "title_art_mode": self.title_art_mode,
            "top_light_mode": self.top_light_mode,
            "top_light_peak": self.top_light_peak,
            "qss_body_mode": self.qss_body_mode,
            "qss_highlight_mode": self.qss_highlight_mode,
            "qss_highlight_peak": self.qss_highlight_peak,
            "luxury_bg_mode": self.luxury_bg_mode,
            "luxury_star_intensity": self.luxury_star_intensity,
            "luxury_script_font_id": self.luxury_script_font_id,
            "luxury_gold_mode": self.luxury_gold_mode,
            "luxury_btn_mode": self.luxury_btn_mode,
        }


def appearance_override_qss(appearance: AppearanceSettings) -> str:
    """Dynamic QSS overrides for global font size (shell fill via painter)."""
    fs = appearance.font_size
    blocks = [f"{sel} {{ font-size: {fs}px !important; }}" for sel in _FONT_OVERRIDE_SELECTORS]
    blocks.append(_NAV_PINNED_FONT_RULE)
    return "\n".join(blocks)
