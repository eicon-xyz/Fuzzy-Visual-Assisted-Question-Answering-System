"""
透明简约水晶玻璃风 — 观感预览 Demo
====================================
左栏 413×636 中窗 1:1 + 右栏样式控制台；外窗 773×636。

运行:  python -m ui.style_preview_demo
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from typing import Literal

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, QRect, QRectF, QPointF, QSize
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QTextEdit,
)

from ui.chat_bubble import ChatBubble
from ui.demo.luxury_icons import luxury_icon
from ui.demo.luxury_title import (
    DEFAULT_SCRIPT_FONT_ID,
    LuxuryScriptTitleWidget,
    script_font_labels,
)
from ui.demo.luxury_paint import (
    BgMode,
    ShellMode,
    TOKENS as LUX_TOKENS,
    paint_luxury_frame,
)
from ui.native.fonts import apply_app_font
from ui.native import crystal_glass as cg
from ui.native.crystal_glass import GLASS_FILL_ALPHA
from ui.native.nav_icons import action_icon, svg_icon
from ui.native.widgets import (
    apply_shell_shadow,
    make_scroll_area_transparent,
    make_widget_transparent,
)
from ui.native.shell_appearance import (
    DEFAULT_CRYSTAL_EDGE_SHADOW,
    SHADOW_STRENGTH_MAX,
    apply_crystal_drop_shadow,
    crystal_fill_alpha_from_percent,
    default_crystal_shadow_strength,
)
from ui.native.shell_paint import (
    DEFAULT_QSS_BODY,
    DEFAULT_QSS_HIGHLIGHT,
    DEFAULT_QSS_HIGHLIGHT_PEAK,
    DEFAULT_LIGHT_MODE,
    LIGHT_MODES,
    QSS_BODY_MODES,
    QSS_HIGHLIGHT_MODES,
    LightMode,
    QssBodyMode,
    QssHighlightMode,
    paint_crystal_shell as paint_demo_crystal_glass,
    paint_qss_shell as paint_demo_qss_shell,
)
from ui.native.title_art import (
    DEFAULT_TITLE_ART,
    TITLE_ART_MODES,
    TitleArtWidget,
)

MEDIUM_W = 413
MEDIUM_H = 636
COMPACT_W = 280
COMPACT_H = 48
CONTROL_W = 360
WINDOW_H = 636
WINDOW_W = MEDIUM_W + CONTROL_W
SHELL_RADIUS = 20
COMPACT_RADIUS = 24
DEMO_TOPBAR_H = 52
DEMO_PANEL_SUB = "操作指引"
ERROR_CHIP_TEXT = "● A端连接失败"

BODY_FONT_PRESETS: dict[str, str] = {
    "system": '"Segoe UI", "Microsoft YaHei UI", sans-serif',
    "source_han": '"Source Han Sans SC", "Microsoft YaHei UI", sans-serif',
    "pingfang": '"PingFang SC", "Microsoft YaHei UI", sans-serif',
    "inter": '"Inter", "Segoe UI", sans-serif',
}

DEFAULT_BODY_FONT = "system"
DEFAULT_TOP_LIGHT_PEAK = 45
DEFAULT_SHELL_LUMINANCE = 100

ACCENTS: dict[str, tuple[str, str, str]] = {
    "accent_a": ("雾蓝 calm", "#5a9ec4", "90, 158, 196"),
    "accent_b": ("青蓝 tech", "#38bdf8", "56, 189, 248"),
    "accent_c": ("紫蓝 premium", "#7c8fd4", "124, 143, 212"),
    "accent_luxury_a": ("黑金 gold", "#C9A84C", "201, 168, 76"),
    "accent_luxury_b": ("香槟 bronze", "#8C7B65", "140, 123, 101"),
    "accent_luxury_c": ("玫瑰 mauve", "#B8A9C9", "184, 169, 201"),
}

BASES: dict[str, tuple[str, str, tuple[int, int, int]]] = {
    "base_a": ("冷蓝黑", "#0f172a", (15, 23, 42)),
    "base_b": ("石墨", "#141820", (20, 24, 32)),
    "base_c": ("暖紫灰", "#1a1625", (26, 22, 37)),
    "base_luxury_a": ("暖近黑", "#0C0B0A", (12, 11, 10)),
    "base_luxury_b": ("香槟底", "#0F0D0B", (15, 13, 11)),
}

LUXURY_PRESETS: dict[str, tuple[str, str, str]] = {
    "luxury_a": ("黑金轻奢（主）", "base_luxury_a", "accent_luxury_a"),
    "luxury_b": ("香槟编辑", "base_luxury_b", "accent_luxury_b"),
    "luxury_c": ("冷调轻奢", "base_a", "accent_luxury_c"),
}


SHELL_PRESETS: dict[str, str] = {
    "qss": "QSS 实底",
    "crystal_edge": "Crystal · 纯细边",
    "crystal_light": "Crystal · 极轻阴影",
}

DEFAULT_ACCENT = "accent_c"
DEFAULT_BASE = "base_a"
DEFAULT_FONT = 12
DEFAULT_SHELL_PRESET = "qss"
DEFAULT_MEDIUM_ALPHA = 87
DEFAULT_COMPACT_ALPHA = 93
QSS_ALPHA_REF = 89

LUXURY_V2_RADIUS_DEFAULT = 10
LUXURY_V2_RADIUS_TIGHT = 6
LUXURY_V2_COMPACT_RADIUS = 12
LUXURY_V2_TITLE_MODES: dict[str, str] = {
    "restrained": "克制白字",
    "gradient": "渐变艺术字",
    "liquid_script": "鎏金签名",
}
DEFAULT_LUXURY_V2_TITLE = "liquid_script"
DEFAULT_LUXURY_SCRIPT_FONT = DEFAULT_SCRIPT_FONT_ID
LUXURY_SCRIPT_FONT_OPTIONS = script_font_labels()
LUXURY_V2_GOLD_MODES: dict[str, str] = {
    "horizontal": "横向扫光",
    "diagonal": "斜向扫光",
    "dual_layer": "双层鎏金",
}
DEFAULT_LUXURY_V2_GOLD = "horizontal"
LUXURY_V2_BTN_MODES: dict[str, str] = {
    "edge": "常驻金边",
    "hover": "hover 金边",
}
DEFAULT_LUXURY_V2_BTN = "edge"

ERROR_BANNER_SHORT = "A 端连接失败 · 请检查校园网/VPN"
ERROR_DETAIL = (
    "内网 A 端不可达 (http://127.0.0.1:8010)。\n\n"
    "请确认校园网/VPN 与系统设置中的地址是否正确。\n\n"
    "如需本地启动，请切换为「本地启动」并运行 CPU OmniParser。"
)
DEMO_SYSTEM_REPLY = (
    "你好！我是 HAJIMI 智能桌面指引助手。"
    "本地模式请切换为「本地启动」并运行 CPU OmniParser。"
)


def _crystal_fill_alpha(alpha_percent: int) -> int:
    return crystal_fill_alpha_from_percent(alpha_percent)


def _lerp_rgb(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


@dataclass
class DemoShellTokens:
    base_rgb: tuple[int, int, int]
    crystal_fill_rgb: tuple[int, int, int]
    medium_fill_alpha: int
    compact_fill_alpha: int
    medium_qss_alpha: float
    compact_qss_alpha: float
    gradient_tint: tuple[int, int, int] | None


def _compute_shell_tokens(
    base_id: str,
    medium_alpha: int,
    compact_alpha: int,
    shell_luminance: int,
) -> DemoShellTokens:
    _blabel, _bhex, base_rgb = _base_info(base_id)
    eff_medium = _effective_alpha(medium_alpha, shell_luminance)
    eff_compact = _effective_alpha(compact_alpha, shell_luminance)
    medium_fill = _crystal_fill_alpha(medium_alpha)
    compact_fill = _crystal_fill_alpha(compact_alpha)

    if base_id == DEFAULT_BASE:
        crystal_fill_rgb = cg.GLASS_FILL_RGB
        gradient_tint = None
    else:
        crystal_fill_rgb = _lerp_rgb(cg.GLASS_FILL_RGB, base_rgb, 0.35)
        gradient_tint = crystal_fill_rgb

    return DemoShellTokens(
        base_rgb=base_rgb,
        crystal_fill_rgb=crystal_fill_rgb,
        medium_fill_alpha=medium_fill,
        compact_fill_alpha=compact_fill,
        medium_qss_alpha=eff_medium / 100.0,
        compact_qss_alpha=eff_compact / 100.0,
        gradient_tint=gradient_tint,
    )


def _is_crystal_preset(shell_preset: str) -> bool:
    return shell_preset.startswith("crystal")


def _accent_rgb_hex(accent_id: str) -> tuple[str, str, str]:
    return ACCENTS.get(accent_id, ACCENTS[DEFAULT_ACCENT])


def _base_info(base_id: str) -> tuple[str, str, tuple[int, int, int]]:
    return BASES.get(base_id, BASES[DEFAULT_BASE])


def _error_tooltip() -> str:
    return f"{ERROR_BANNER_SHORT}\n\n{ERROR_DETAIL}"


def _effective_alpha(alpha_percent: int, luminance: int) -> int:
    return max(50, min(95, int(alpha_percent * luminance / 100)))


def _scale_luminance_rgb(r: int, g: int, b: int, luminance: int) -> tuple[int, int, int]:
    t = luminance / 100.0
    if t <= 1.0:
        return (int(r * t), int(g * t), int(b * t))

    def lift(c: int) -> int:
        return min(255, int(c + (255 - c) * (t - 1.0) * 0.25))

    return (lift(r), lift(g), lift(b))


def _coerce_int_prop(widget: QWidget, name: str, default: int) -> int:
    value = widget.property(name)
    if value is None or value == "":
        return default
    return int(value)


def _apply_demo_crystal_shell(
    widget: "DemoShellWidget",
    tokens: DemoShellTokens,
    *,
    compact: bool,
    shadow_strength: int,
    light_mode: LightMode,
    top_light_peak: int,
    shell_luminance: int,
) -> None:
    fill_alpha = tokens.compact_fill_alpha if compact else tokens.medium_fill_alpha
    widget._demo_crystal_active = True
    widget._demo_shell_compact = compact
    widget._demo_crystal_fill_rgb = tokens.crystal_fill_rgb
    widget._demo_crystal_fill_alpha = fill_alpha
    widget._demo_gradient_tint = tokens.gradient_tint
    widget._demo_qss_rgba = None
    widget.setProperty("_demo_crystal_shadow_strength", shadow_strength)
    widget.setProperty("_demo_light_mode", light_mode)
    widget.setProperty("_demo_top_light_peak", top_light_peak)
    widget.setProperty("_demo_shell_luminance", shell_luminance)
    apply_crystal_drop_shadow(widget, shadow_strength)
    widget.setAutoFillBackground(False)
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setAttribute(Qt.WA_TranslucentBackground, True)
    widget.update()


def _apply_demo_qss_shell(
    widget: "DemoShellWidget",
    tokens: DemoShellTokens,
    *,
    compact: bool,
    body_mode: QssBodyMode,
    highlight_mode: QssHighlightMode,
    highlight_peak: int,
) -> None:
    qss_alpha = tokens.compact_qss_alpha if compact else tokens.medium_qss_alpha
    r, g, b = tokens.base_rgb
    widget._demo_crystal_active = False
    widget._demo_shell_compact = compact
    widget._demo_qss_rgba = (r, g, b, int(qss_alpha * 255))
    widget._demo_qss_body_mode = body_mode
    widget._demo_qss_highlight_mode = highlight_mode
    widget._demo_qss_highlight_peak = highlight_peak
    widget._demo_crystal_fill_rgb = None
    widget._demo_crystal_fill_alpha = None
    widget._demo_gradient_tint = None
    widget.setAutoFillBackground(False)
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setAttribute(Qt.WA_TranslucentBackground, False)
    apply_shell_shadow(widget)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


@dataclass
class DemoTopBarResult:
    bar: QWidget
    menu_btn: QPushButton
    title_art: TitleArtWidget
    title_restrained: QLabel
    title_script: LuxuryScriptTitleWidget
    title_sep: QLabel
    panel_sub: QLabel
    error_chip: QLabel
    status_badge: QPushButton


def _build_demo_topbar(parent: QWidget | None = None) -> DemoTopBarResult:
    """Demo-only top bar: art title + panel sub, inline error chip, ghost menu."""
    bar = QWidget(parent)
    bar.setObjectName("TopBar")
    bar.setMinimumHeight(DEMO_TOPBAR_H)
    bar.setMaximumHeight(DEMO_TOPBAR_H)

    layout = QHBoxLayout(bar)
    layout.setContentsMargins(16, 8, 16, 8)
    layout.setSpacing(12)

    menu_btn = QPushButton("☰", bar)
    menu_btn.setObjectName("MenuBtn")
    menu_btn.setFixedSize(34, 34)
    menu_btn.setFlat(True)
    layout.addWidget(menu_btn)

    text_wrap = QWidget(bar)
    text_wrap.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    text_row = QHBoxLayout(text_wrap)
    text_row.setContentsMargins(0, 0, 0, 0)
    text_row.setSpacing(6)

    title_restrained = QLabel("HAJIMI", text_wrap)
    title_restrained.setObjectName("TopTitleRestrained")
    title_restrained.hide()
    text_row.addWidget(title_restrained)

    title_art = TitleArtWidget(text_wrap)
    text_row.addWidget(title_art)

    title_script = LuxuryScriptTitleWidget(text_wrap)
    title_script.hide()
    text_row.addWidget(title_script)

    title_sep = QLabel("·", text_wrap)
    title_sep.setObjectName("TopTitleSep")
    text_row.addWidget(title_sep)

    panel_sub = QLabel(DEMO_PANEL_SUB, text_wrap)
    panel_sub.setObjectName("TopSub")
    panel_sub.setMinimumWidth(0)
    panel_sub.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    text_row.addWidget(panel_sub)

    layout.addWidget(text_wrap)

    error_chip = QLabel(ERROR_CHIP_TEXT, bar)
    error_chip.setObjectName("TopErrorChip")
    error_chip.setToolTip(_error_tooltip())
    error_chip.hide()
    layout.addWidget(error_chip)

    layout.addStretch(1)

    status_badge = QPushButton("●  准备就绪", bar)
    status_badge.setObjectName("StatusBadge")
    status_badge.setProperty("status", "idle")
    status_badge.setFlat(True)
    layout.addWidget(status_badge)

    return DemoTopBarResult(
        bar=bar,
        menu_btn=menu_btn,
        title_art=title_art,
        title_restrained=title_restrained,
        title_script=title_script,
        title_sep=title_sep,
        panel_sub=panel_sub,
        error_chip=error_chip,
        status_badge=status_badge,
    )


def compose_luxury_v2_qss(
    font_size: int,
    body_font_id: str = DEFAULT_BODY_FONT,
    *,
    shell_radius: int = LUXURY_V2_RADIUS_DEFAULT,
    compact_radius: int = LUXURY_V2_COMPACT_RADIUS,
    send_btn_style: str = DEFAULT_LUXURY_V2_BTN,
) -> str:
    body_font = BODY_FONT_PRESETS.get(body_font_id, BODY_FONT_PRESETS[DEFAULT_BODY_FONT])
    bubble_label = font_size + 1
    gold = LUX_TOKENS.gold
    send_name = "LuxBtnGoldEdge" if send_btn_style == "edge" else "LuxBtnGoldHover"
    return f"""
* {{
    font-family: {body_font};
    font-size: {font_size}px;
    color: {LUX_TOKENS.secondary};
}}
QWidget#NativeShell, QWidget#CompactShell {{
    background: transparent;
    background-color: transparent;
    border: none;
    border-radius: {shell_radius}px;
}}
QWidget#TopBar {{
    background: transparent;
    border-bottom: 1px solid {LUX_TOKENS.surface_line};
}}
QWidget#TitleArt, QWidget#LuxuryScriptTitle {{
    background: transparent;
}}
QLabel#TopTitleRestrained {{
    font-size: 13px;
    font-weight: 600;
    color: {LUX_TOKENS.secondary};
    background: transparent;
}}
QLabel#TopSub {{
    font-size: 12px;
    color: {LUX_TOKENS.secondary_muted};
    font-weight: 500;
}}
QLabel#TopTitleSep {{
    font-size: 12px;
    color: {LUX_TOKENS.secondary_muted};
    padding: 0 2px;
}}
QLabel#TopErrorChip {{
    font-size: 11px;
    font-weight: 600;
    color: #e74c3c;
}}
QPushButton#StatusBadge {{
    padding: 6px 16px;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 600;
    background: rgba(255, 255, 255, 0.05);
    color: {LUX_TOKENS.secondary_muted};
    border: none;
}}
QPushButton#StatusBadge[status="processing"] {{
    background: rgba(201, 168, 76, 0.12);
    color: {gold};
}}
QPushButton#MenuBtn, QPushButton#LuxIconBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    min-width: 34px;
    min-height: 34px;
    color: {LUX_TOKENS.secondary_muted};
    font-size: 16px;
}}
QPushButton#MenuBtn:hover, QPushButton#LuxIconBtn:hover {{
    background: rgba(255, 255, 255, 0.05);
}}
QScrollArea#PreviewContent, QWidget#PreviewContentWrap, QWidget#InputDock {{
    background: transparent;
    border: none;
}}
QFrame#bubble-user {{
    background-color: #1C1916;
    border: 1px solid {LUX_TOKENS.surface_line};
    border-radius: 10px;
    border-top-right-radius: 2px;
}}
QFrame#bubble-system {{
    background-color: {LUX_TOKENS.bg_elevated};
    border: 1px solid {LUX_TOKENS.surface_line};
    border-radius: 10px;
    border-top-left-radius: 2px;
}}
QLabel#bubbleUserLabel, QLabel#bubbleSystemLabel {{
    color: {LUX_TOKENS.secondary};
    font-size: {bubble_label}px;
}}
QFrame#InputFloat {{
    background: {LUX_TOKENS.bg_elevated};
    border: 1px solid {LUX_TOKENS.surface_line};
    border-radius: 10px;
}}
QPushButton#IconBtnGhost, QPushButton#LuxIconBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
}}
QFrame#InputFloat QTextEdit#ChatInput {{
    background: transparent;
    border: none;
    color: {LUX_TOKENS.secondary};
    font-size: {font_size}px;
}}
QPushButton#LuxBtnGoldEdge, QPushButton#SendBtnLuxEdge {{
    background: {LUX_TOKENS.bg_elevated};
    border: 1px solid {gold};
    border-radius: 8px;
    color: {LUX_TOKENS.secondary};
    font-size: 14px;
    min-width: 32px;
    min-height: 32px;
}}
QPushButton#LuxBtnGoldHover, QPushButton#SendBtnLuxHover {{
    background: {LUX_TOKENS.bg_elevated};
    border: 1px solid rgba(201, 168, 76, 0.25);
    border-radius: 8px;
    color: {LUX_TOKENS.secondary};
    font-size: 14px;
    min-width: 32px;
    min-height: 32px;
}}
QPushButton#LuxBtnGoldHover:hover, QPushButton#SendBtnLuxHover:hover {{
    border: 1px solid {gold};
    background: rgba(201, 168, 76, 0.08);
}}
QPushButton#{send_name} {{
    background: {LUX_TOKENS.bg_elevated};
    border: 1px solid {gold if send_btn_style == "edge" else "rgba(201, 168, 76, 0.25)"};
    border-radius: 8px;
    color: {LUX_TOKENS.secondary};
}}
QLineEdit#CompactInput {{
    background: transparent;
    border: none;
    color: {LUX_TOKENS.secondary};
}}
QLabel#CompactHint {{
    color: {LUX_TOKENS.secondary_muted};
}}
QWidget#ControlPanel {{
    background: #141820;
}}
QLabel#ControlTitle, QLabel#SectionLabel {{
    color: #f1f5f9;
}}
QLabel#DemoHint, QLabel#SliderValue {{
    color: #94a3b8;
}}
QPushButton#DemoActionBtn {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    color: #e2e8f0;
    padding: 6px 10px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 4px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.08);
    border-radius: 4px;
}}
"""


def compose_demo_qss(
    accent_id: str,
    shell_preset: str,
    base_id: str,
    medium_alpha: int,
    compact_alpha: int,
    font_size: int,
    body_font_id: str = DEFAULT_BODY_FONT,
    shell_luminance: int = DEFAULT_SHELL_LUMINANCE,
) -> str:
    _alabel, accent, accent_rgb = _accent_rgb_hex(accent_id)
    blabel, bhex, (br, bg, bb) = _base_info(base_id)
    eff_medium = _effective_alpha(medium_alpha, shell_luminance)
    eff_compact = _effective_alpha(compact_alpha, shell_luminance)
    ma = eff_medium / 100.0
    ca = eff_compact / 100.0
    body_font = BODY_FONT_PRESETS.get(body_font_id, BODY_FONT_PRESETS[DEFAULT_BODY_FONT])
    accent_soft = f"rgba({accent_rgb}, 0.15)"
    accent_hover = f"rgba({accent_rgb}, 0.10)"
    bubble_label = font_size + 1

    if _is_crystal_preset(shell_preset):
        shell_block = f"""
QWidget#NativeShell {{
    background: transparent;
    background-color: transparent;
    border: none;
    border-radius: {SHELL_RADIUS}px;
}}
QWidget#CompactShell {{
    background: transparent;
    background-color: transparent;
    border: none;
    border-radius: {COMPACT_RADIUS}px;
}}
"""
    else:
        shell_block = f"""
QWidget#NativeShell {{
    background: transparent;
    background-color: transparent;
    border: none;
    border-radius: {SHELL_RADIUS}px;
}}
QWidget#CompactShell {{
    background: transparent;
    background-color: transparent;
    border: none;
    border-radius: {COMPACT_RADIUS}px;
}}
"""

    return f"""
* {{
    font-family: {body_font};
    font-size: {font_size}px;
}}
{shell_block}
QWidget#TopBar {{
    background: transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}}
QWidget#TitleArt, QWidget#LuxuryScriptTitle {{
    background: transparent;
}}
QLabel#TopSub {{
    font-size: 12px;
    color: #94a3b8;
    font-weight: 500;
}}
QLabel#TopTitleSep {{
    font-size: 12px;
    color: #64748b;
    font-weight: 500;
    padding: 0 2px;
}}
QLabel#TopErrorChip {{
    font-size: 11px;
    font-weight: 600;
    color: #e74c3c;
    padding-left: 4px;
}}
QPushButton#StatusBadge {{
    padding: 6px 16px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    background: rgba(255, 255, 255, 0.06);
    color: #94a3b8;
    border: none;
}}
QPushButton#StatusBadge:hover {{
    background: rgba(255, 255, 255, 0.09);
}}
QPushButton#StatusBadge[status="processing"] {{
    background: rgba({accent_rgb}, 0.2);
    color: {accent};
}}
QPushButton#MenuBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    min-width: 34px;
    min-height: 34px;
    padding: 0;
}}
QPushButton#MenuBtn:hover,
QPushButton#MenuBtn[open="true"] {{
    background: rgba(255, 255, 255, 0.06);
    border: none;
}}
QScrollArea#PreviewContent {{
    background: transparent;
    border: none;
}}
QScrollArea#PreviewContent QAbstractScrollArea::viewport {{
    background: transparent;
}}
QWidget#PreviewContentWrap,
QWidget#InputDock {{
    background: transparent;
    border: none;
}}
QFrame#bubble-user {{
    background-color: {accent};
    border-radius: 12px;
    border-top-right-radius: 2px;
}}
QFrame#bubble-system {{
    background-color: rgba(30, 41, 59, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    border-top-left-radius: 2px;
}}
QLabel#bubbleUserLabel {{
    color: #ffffff;
    font-size: {bubble_label}px;
}}
QLabel#bubbleSystemLabel {{
    color: #f1f5f9;
    font-size: {bubble_label}px;
}}
QFrame#InputFloat {{
    background: rgba(30, 41, 59, 0.50);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
}}
QPushButton#IconBtnGhost {{
    background: transparent;
    border: none;
    border-radius: 10px;
    color: #64748b;
    font-size: 14px;
}}
QPushButton#IconBtnGhost:disabled {{
    color: #475569;
}}
QFrame#InputFloat QTextEdit#ChatInput {{
    background: transparent;
    border: none;
    color: #f1f5f9;
    font-size: {font_size}px;
}}
QPushButton#SendBtnAccent {{
    background: transparent;
    border: none;
    border-radius: 10px;
    color: {accent};
    font-size: 16px;
}}
QPushButton#SendBtnAccent:hover {{
    background: {accent_hover};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(255, 255, 255, 0.18);
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
    background: transparent;
}}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    height: 0;
    background: transparent;
}}
QLabel#CompactMark {{
    background: {accent_soft};
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    color: {accent};
    font-size: 13px;
}}
QLineEdit#CompactInput {{
    background: transparent;
    border: none;
    color: #f1f5f9;
    font-size: {font_size}px;
}}
QLabel#CompactHint {{
    color: #64748b;
    font-size: 10px;
}}
QWidget#LeftPane {{
    background: transparent;
}}
QWidget#ControlPanel {{
    background: rgba(15, 23, 42, 0.96);
    border-left: 1px solid rgba(255, 255, 255, 0.08);
}}
QLabel#ControlTitle {{
    color: #94a3b8;
    font-size: 11px;
    font-weight: 600;
}}
QRadioButton {{
    color: #f1f5f9;
    font-size: 11px;
    spacing: 4px;
}}
QLabel#DemoHint {{
    color: #64748b;
    font-size: 10px;
}}
QLabel#ScaleBadge {{
    color: #94a3b8;
    font-size: 9px;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 4px 8px;
}}
QLabel#SliderValue {{
    color: #64748b;
    font-size: 10px;
    min-width: 32px;
}}
QPushButton#DemoActionBtn {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px;
    color: #f1f5f9;
    font-size: 11px;
    padding: 6px 10px;
}}
QPushButton#DemoActionBtn:hover {{
    background: rgba(255, 255, 255, 0.10);
}}
QLabel#SectionLabel {{
    color: #64748b;
    font-size: 10px;
    font-weight: 600;
    padding-top: 4px;
}}
"""


class BusyDesktopBackground(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(45, 75, 120))
        grad.setColorAt(0.5, QColor(90, 130, 180))
        grad.setColorAt(1.0, QColor(30, 50, 85))
        painter.fillRect(self.rect(), QBrush(grad))

        blocks = [
            (12, 40, 120, 90, QColor(240, 240, 245, 200)),
            (220, 20, 100, 70, QColor(255, 255, 255, 190)),
            (40, 260, 140, 100, QColor(255, 255, 255, 170)),
            (250, 380, 90, 60, QColor(235, 240, 250, 190)),
            (20, 500, 160, 70, QColor(200, 210, 230, 180)),
        ]
        painter.setPen(Qt.NoPen)
        for x, y, bw, bh, color in blocks:
            painter.setBrush(color)
            painter.drawRoundedRect(x, y, bw, bh, 8, 8)
        painter.end()


class DemoShellWidget(QWidget):
    """Demo shell: demo-owned QSS fill or crystal paint (no production shell_renderer)."""

    def __init__(self, parent=None, *, compact: bool = False):
        super().__init__(parent)
        self._demo_crystal_active = False
        self._demo_shell_compact = compact
        self._demo_qss_rgba: tuple[int, int, int, int] | None = None
        self._demo_crystal_fill_rgb: tuple[int, int, int] | None = None
        self._demo_crystal_fill_alpha: int | None = None
        self._demo_gradient_tint: tuple[int, int, int] | None = None
        self._demo_qss_body_mode: QssBodyMode = DEFAULT_QSS_BODY
        self._demo_qss_highlight_mode: QssHighlightMode = DEFAULT_QSS_HIGHLIGHT
        self._demo_qss_highlight_peak: int = DEFAULT_QSS_HIGHLIGHT_PEAK

    def _luxury_v2_active(self) -> bool:
        return bool(
            getattr(self, "_luxury_v2_enabled", False)
            or self.property("_luxury_v2_enabled")
        )

    def _shell_radius(self) -> float:
        if self._luxury_v2_active():
            raw = getattr(self, "_luxury_radius", None) or self.property("_luxury_radius")
            return float(raw or LUXURY_V2_RADIUS_DEFAULT)
        return COMPACT_RADIUS if self._demo_shell_compact else SHELL_RADIUS

    def _paint_luxury_v2(self, painter: QPainter) -> None:
        rect = QRectF(self.rect())
        bg_mode: BgMode = (
            getattr(self, "_luxury_bg_mode", None)
            or self.property("_luxury_bg_mode")
            or "frosted"
        )
        shell_mode: ShellMode = (
            getattr(self, "_luxury_shell_mode", None)
            or self.property("_luxury_shell_mode")
            or "SA"
        )
        raw_intensity = getattr(self, "_luxury_star_intensity", None) or self.property(
            "_luxury_star_intensity"
        )
        intensity = int(raw_intensity or 60)
        raw_radius = getattr(self, "_luxury_radius", None) or self.property("_luxury_radius")
        radius = float(raw_radius or LUXURY_V2_RADIUS_DEFAULT)
        paint_luxury_frame(
            painter,
            rect,
            bg_mode=bg_mode,
            shell_mode=shell_mode,
            star_intensity=intensity,
            radius=radius,
            compact=self._demo_shell_compact,
        )

    def _paint_qss_shell(self, painter: QPainter) -> None:
        if not self._demo_qss_rgba:
            return
        paint_demo_qss_shell(
            painter,
            float(self.width()),
            float(self.height()),
            rgba=self._demo_qss_rgba,
            body_mode=self._demo_qss_body_mode,
            highlight_mode=self._demo_qss_highlight_mode,
            highlight_peak=self._demo_qss_highlight_peak,
            radius=self._shell_radius(),
            compact=self._demo_shell_compact,
        )

    def paintEvent(self, event):
        if self._luxury_v2_active():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            self._paint_luxury_v2(painter)
            painter.end()
            return
        if self._demo_crystal_active:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            light_mode = str(self.property("_demo_light_mode") or DEFAULT_LIGHT_MODE)
            paint_demo_crystal_glass(
                painter,
                float(self.width()),
                float(self.height()),
                compact=self._demo_shell_compact,
                fill_rgb=self._demo_crystal_fill_rgb,
                fill_alpha=self._demo_crystal_fill_alpha,
                light_mode=light_mode,
                top_light_peak=_coerce_int_prop(self, "_demo_top_light_peak", DEFAULT_TOP_LIGHT_PEAK),
                shell_luminance=_coerce_int_prop(self, "_demo_shell_luminance", DEFAULT_SHELL_LUMINANCE),
                gradient_tint=self._demo_gradient_tint,
            )
            painter.end()
            return
        if self._demo_qss_rgba:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            self._paint_qss_shell(painter)
            painter.end()
            return
        super().paintEvent(event)


class MediumMock(DemoShellWidget):
    """413×636 medium panel — demo topbar, bubbles, input dock."""

    def __init__(self, parent=None):
        super().__init__(parent, compact=False)
        self.setObjectName("NativeShell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(MEDIUM_W, MEDIUM_H)

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        top = _build_demo_topbar(self)
        make_widget_transparent(top.bar)
        self.title_art = top.title_art
        self.title_restrained = top.title_restrained
        self.title_script = top.title_script
        self.title_sep = top.title_sep
        self.menu_btn = top.menu_btn
        self.status_badge = top.status_badge
        self.error_chip = top.error_chip
        col.addWidget(top.bar)

        scroll = QScrollArea()
        scroll.setObjectName("PreviewContent")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        make_scroll_area_transparent(scroll)

        wrap = QWidget()
        wrap.setObjectName("PreviewContentWrap")
        make_widget_transparent(wrap)
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(14, 10, 14, 10)
        wl.setSpacing(10)

        wl.addWidget(ChatBubble(DEMO_SYSTEM_REPLY, "system"))
        wl.addWidget(ChatBubble("怎么安装微信？", "user"))
        wl.addStretch()
        scroll.setWidget(wrap)
        col.addWidget(scroll, 1)

        dock = QWidget()
        dock.setObjectName("InputDock")
        make_widget_transparent(dock)
        dl = QVBoxLayout(dock)
        dl.setContentsMargins(10, 0, 10, 10)
        float_frame = QFrame()
        float_frame.setObjectName("InputFloat")
        float_frame.setAttribute(Qt.WA_StyledBackground, True)
        fl = QHBoxLayout(float_frame)
        fl.setContentsMargins(12, 8, 12, 8)
        fl.setSpacing(8)

        mic_btn = QPushButton()
        mic_btn.setObjectName("IconBtnGhost")
        mic_btn.setIcon(action_icon("mic"))
        mic_btn.setFixedSize(32, 32)
        mic_btn.setEnabled(False)
        mic_btn.setToolTip("语音（即将推出）")
        self.mic_btn = mic_btn

        inp = QTextEdit()
        inp.setObjectName("ChatInput")
        inp.setPlaceholderText("输入问题…")
        inp.setFixedHeight(30)
        inp.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        send = QPushButton("➤")
        send.setObjectName("SendBtnAccent")
        send.setFixedSize(32, 32)
        self.send_btn = send

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(send)

        fl.addWidget(mic_btn)
        fl.addWidget(inp, 1)
        fl.addLayout(actions)
        dl.addWidget(float_frame)
        col.addWidget(dock)


class CompactMock(DemoShellWidget):
    """280×48 compact pill preview."""

    def __init__(self, parent=None):
        super().__init__(parent, compact=True)
        self.setObjectName("CompactShell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(COMPACT_W, COMPACT_H)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 6, 4)
        layout.setSpacing(8)

        mark = QLabel("✦")
        mark.setObjectName("CompactMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(26, 26)
        layout.addWidget(mark)

        inp = QLineEdit()
        inp.setObjectName("CompactInput")
        inp.setPlaceholderText("Ask HAJIMI…")
        layout.addWidget(inp, 1)

        hint = QLabel("↵")
        hint.setObjectName("CompactHint")
        layout.addWidget(hint)


class StylePreviewWindow(QWidget):
    """Left: 413×636 medium on busy desktop. Right: style control panel."""

    def __init__(self):
        super().__init__()
        self._accent_id = DEFAULT_ACCENT
        self._base_id = DEFAULT_BASE
        self._shell_preset = DEFAULT_SHELL_PRESET
        self._font_size = DEFAULT_FONT
        self._medium_alpha = DEFAULT_MEDIUM_ALPHA
        self._compact_alpha = DEFAULT_COMPACT_ALPHA
        self._processing = False
        self._system_error = False
        self._title_art_mode = DEFAULT_TITLE_ART
        self._body_font_id = DEFAULT_BODY_FONT
        self._light_mode: LightMode = DEFAULT_LIGHT_MODE
        self._top_light_peak = DEFAULT_TOP_LIGHT_PEAK
        self._shell_luminance = DEFAULT_SHELL_LUMINANCE
        self._qss_body_mode: QssBodyMode = DEFAULT_QSS_BODY
        self._qss_highlight_mode: QssHighlightMode = DEFAULT_QSS_HIGHLIGHT
        self._qss_highlight_peak = DEFAULT_QSS_HIGHLIGHT_PEAK
        self._crystal_shadow_strength = DEFAULT_CRYSTAL_EDGE_SHADOW

        self._luxury_v2_enabled = False
        self._luxury_bg_mode: BgMode = "frosted"
        self._luxury_shell_mode: ShellMode = "SA"
        self._luxury_star_intensity = 60
        self._luxury_radius = LUXURY_V2_RADIUS_DEFAULT
        self._luxury_v2_title_mode = DEFAULT_LUXURY_V2_TITLE
        self._luxury_script_font_id = DEFAULT_LUXURY_SCRIPT_FONT
        self._luxury_v2_gold_mode = DEFAULT_LUXURY_V2_GOLD
        self._luxury_v2_btn_mode = DEFAULT_LUXURY_V2_BTN

        self.setWindowTitle("HAJIMI · 水晶玻璃风观感 Demo")
        self.setFixedSize(WINDOW_W, WINDOW_H)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QWidget()
        left.setObjectName("LeftPane")
        left.setFixedSize(MEDIUM_W, WINDOW_H)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._bg = BusyDesktopBackground()
        left_layout.addWidget(self._bg)

        medium_host = QWidget(self._bg)
        medium_host.setAttribute(Qt.WA_TranslucentBackground, True)
        mh_layout = QVBoxLayout(medium_host)
        mh_layout.setContentsMargins(0, 0, 0, 0)
        self._medium = MediumMock()
        mh_layout.addWidget(self._medium, 0, Qt.AlignTop | Qt.AlignHCenter)

        self._scale_badge = QLabel()
        self._scale_badge.setObjectName("ScaleBadge")
        badge_layout = QHBoxLayout()
        badge_layout.setContentsMargins(6, 0, 6, 6)
        badge_layout.addStretch()
        badge_layout.addWidget(self._scale_badge)
        mh_layout.addLayout(badge_layout)
        self._medium_host = medium_host

        root.addWidget(left)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(CONTROL_W)

        self._compact = CompactMock()
        self._control = self._build_controls()
        scroll.setWidget(self._control)
        root.addWidget(scroll)

        self._setup_badge_pulse()
        self._apply_preview()

    def showEvent(self, event):
        super().showEvent(event)
        self._medium_host.setGeometry(0, 0, MEDIUM_W, WINDOW_H)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._medium_host.setGeometry(0, 0, MEDIUM_W, WINDOW_H)

    def _refresh_left_preview(self) -> None:
        self._medium_host.setGeometry(0, 0, MEDIUM_W, WINDOW_H)
        self._medium_host.raise_()
        self._medium_host.show()
        self._medium.show()
        for widget in (self._medium, self._compact):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.repaint()
        self._medium_host.repaint()

    def _compute_tokens(self) -> DemoShellTokens:
        return _compute_shell_tokens(
            self._base_id,
            self._medium_alpha,
            self._compact_alpha,
            self._shell_luminance,
        )

    def _sync_top_light_controls(self) -> None:
        crystal = _is_crystal_preset(self._shell_preset)
        for btn in self._light_group.buttons():
            btn.setEnabled(crystal)
        self._top_light_slider.setEnabled(crystal)
        self._top_light_hint.setVisible(not crystal)

    def _sync_qss_highlight_controls(self) -> None:
        qss = self._shell_preset == "qss"
        for btn in self._qss_body_group.buttons():
            btn.setEnabled(qss)
        for btn in self._qss_highlight_group.buttons():
            btn.setEnabled(qss)
        self._qss_highlight_slider.setEnabled(qss)
        self._qss_highlight_hint.setVisible(not qss)

    def _sync_shadow_controls(self) -> None:
        crystal = _is_crystal_preset(self._shell_preset)
        self._shadow_slider.setEnabled(crystal)
        self._shadow_hint.setVisible(not crystal)

    def _update_hint_labels(self) -> None:
        preset = self._shell_preset
        tokens = self._compute_tokens()
        alabel, hex_color, _ = _accent_rgb_hex(self._accent_id)
        blabel, bhex, _ = _base_info(self._base_id)
        shell_label = SHELL_PRESETS.get(preset, preset)
        eff_m = _effective_alpha(self._medium_alpha, self._shell_luminance)
        eff_c = _effective_alpha(self._compact_alpha, self._shell_luminance)
        self._medium_alpha_label.setText(f"{eff_m / 100:.2f}")
        self._compact_alpha_label.setText(f"{eff_c / 100:.2f}")
        self._top_light_label.setText(str(self._top_light_peak))
        self._shadow_label.setText(str(self._crystal_shadow_strength))
        self._qss_highlight_label.setText(str(self._qss_highlight_peak))
        self._luminance_label.setText(f"{self._shell_luminance}%")
        self._scale_badge.setText(f"{MEDIUM_W}×{MEDIUM_H} px · 逻辑像素")
        if self._luxury_v2_enabled:
            bg_label = "磨砂黑" if self._luxury_bg_mode == "frosted" else "牛皮纸黑"
            shell_labels = {"SA": "S-A 半透明", "SB": "S-B 实色卡", "SC": "S-C 铺满"}
            title_label = LUXURY_V2_TITLE_MODES.get(
                self._luxury_v2_title_mode, self._luxury_v2_title_mode
            )
            script_label = LUXURY_SCRIPT_FONT_OPTIONS.get(
                self._luxury_script_font_id, self._luxury_script_font_id
            )
            gold_label = LUXURY_V2_GOLD_MODES.get(
                self._luxury_v2_gold_mode, self._luxury_v2_gold_mode
            )
            btn_label = LUXURY_V2_BTN_MODES.get(self._luxury_v2_btn_mode, self._luxury_v2_btn_mode)
            star_note = (
                f"星空 {self._luxury_star_intensity}"
                if self._luxury_bg_mode == "frosted"
                else "无星空"
            )
            script_note = script_label if self._luxury_v2_title_mode == "liquid_script" else ""
            self._hint.setText(
                f"轻奢 v2 · {bg_label} · {shell_labels.get(self._luxury_shell_mode, '')} · "
                f"{star_note} · 圆角 {int(self._luxury_radius)}px · "
                f"标题 {title_label}"
                + (f" · 签名 {script_note}" if script_note else "")
                + f" · 鎏金 {gold_label} · 按钮 {btn_label} · 70/20/10 黑金"
            )
            self.setWindowTitle("HAJIMI Demo · 轻奢 v2 大改")
            return
        light_label = LIGHT_MODES.get(self._light_mode, self._light_mode)
        font_label = self._body_font_id.replace("_", " ")
        title_label = TITLE_ART_MODES.get(self._title_art_mode, self._title_art_mode)
        if _is_crystal_preset(preset):
            eff_fill = max(
                1,
                min(255, int(tokens.medium_fill_alpha * self._shell_luminance / 100)),
            )
            shell_note = (
                f"Crystal fill α {eff_fill} · 顶光 {light_label} · "
                f"阴影 {self._crystal_shadow_strength}"
            )
        else:
            body_label = QSS_BODY_MODES.get(self._qss_body_mode, self._qss_body_mode)
            hi_label = QSS_HIGHLIGHT_MODES.get(
                self._qss_highlight_mode, self._qss_highlight_mode
            )
            shell_note = (
                f"QSS {body_label} · {hi_label}@{self._qss_highlight_peak} · "
                f"α {eff_m / 100:.2f}"
            )
        self._hint.setText(
            f"底 {blabel} ({bhex}) · 中窗 {shell_note} · "
            f"小窗 α {eff_c / 100:.2f} · 字号 {self._font_size}px · "
            f"标题 {title_label} · 字体 {font_label} · 强调 {alabel} · {shell_label}"
        )
        self.setWindowTitle(
            f"HAJIMI Demo · {MEDIUM_W}×{MEDIUM_H} · {hex_color} · {shell_label}"
        )

    def _apply_crystal_light_only(self) -> bool:
        if not _is_crystal_preset(self._shell_preset):
            return False
        tokens = self._compute_tokens()
        _apply_demo_crystal_shell(
            self._medium,
            tokens,
            compact=False,
            shadow_strength=self._crystal_shadow_strength,
            light_mode=self._light_mode,
            top_light_peak=self._top_light_peak,
            shell_luminance=self._shell_luminance,
        )
        _apply_demo_crystal_shell(
            self._compact,
            tokens,
            compact=True,
            shadow_strength=self._crystal_shadow_strength,
            light_mode=self._light_mode,
            top_light_peak=self._top_light_peak,
            shell_luminance=self._shell_luminance,
        )
        self._medium.repaint()
        self._compact.repaint()
        self._update_hint_labels()
        return True

    def _apply_crystal_shadow_only(self) -> bool:
        if not _is_crystal_preset(self._shell_preset):
            return False
        strength = self._crystal_shadow_strength
        for widget in (self._medium, self._compact):
            widget.setProperty("_demo_crystal_shadow_strength", strength)
            _apply_crystal_drop_shadow(widget, strength)
            widget.update()
        self._medium.repaint()
        self._compact.repaint()
        self._update_hint_labels()
        return True

    def _apply_qss_highlight_only(self) -> bool:
        if self._shell_preset != "qss":
            return False
        tokens = self._compute_tokens()
        _apply_demo_qss_shell(
            self._medium,
            tokens,
            compact=False,
            body_mode=self._qss_body_mode,
            highlight_mode=self._qss_highlight_mode,
            highlight_peak=self._qss_highlight_peak,
        )
        _apply_demo_qss_shell(
            self._compact,
            tokens,
            compact=True,
            body_mode=self._qss_body_mode,
            highlight_mode=self._qss_highlight_mode,
            highlight_peak=self._qss_highlight_peak,
        )
        self._medium.repaint()
        self._compact.repaint()
        self._update_hint_labels()
        return True

    def _apply_shell_from_tokens(self, tokens: DemoShellTokens) -> None:
        preset = self._shell_preset
        if preset == "qss":
            _apply_demo_qss_shell(
                self._medium,
                tokens,
                compact=False,
                body_mode=self._qss_body_mode,
                highlight_mode=self._qss_highlight_mode,
                highlight_peak=self._qss_highlight_peak,
            )
            _apply_demo_qss_shell(
                self._compact,
                tokens,
                compact=True,
                body_mode=self._qss_body_mode,
                highlight_mode=self._qss_highlight_mode,
                highlight_peak=self._qss_highlight_peak,
            )
        else:
            _apply_demo_crystal_shell(
                self._medium,
                tokens,
                compact=False,
                shadow_strength=self._crystal_shadow_strength,
                light_mode=self._light_mode,
                top_light_peak=self._top_light_peak,
                shell_luminance=self._shell_luminance,
            )
            _apply_demo_crystal_shell(
                self._compact,
                tokens,
                compact=True,
                shadow_strength=self._crystal_shadow_strength,
                light_mode=self._light_mode,
                top_light_peak=self._top_light_peak,
                shell_luminance=self._shell_luminance,
            )

    def _setup_badge_pulse(self):
        badge = self._medium.status_badge
        self._badge_fx = QGraphicsOpacityEffect(badge)
        badge.setGraphicsEffect(self._badge_fx)
        self._badge_fx.setOpacity(1.0)

        fade_in = QPropertyAnimation(self._badge_fx, b"opacity", self)
        fade_in.setDuration(1200)
        fade_in.setStartValue(0.72)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InOutSine)

        fade_out = QPropertyAnimation(self._badge_fx, b"opacity", self)
        fade_out.setDuration(1200)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.72)
        fade_out.setEasingCurve(QEasingCurve.InOutSine)

        self._breath_group = QSequentialAnimationGroup(self)
        self._breath_group.addAnimation(fade_in)
        self._breath_group.addAnimation(fade_out)
        self._breath_group.setLoopCount(-1)

    def _set_status_property(self, badge: QPushButton, status: str) -> None:
        badge.setProperty("status", status)
        badge.style().unpolish(badge)
        badge.style().polish(badge)

    def _refresh_status_ui(self) -> None:
        badge = self._medium.status_badge
        chip = self._medium.error_chip
        if self._system_error:
            chip.show()
            chip.setToolTip(_error_tooltip())
            badge.setText("●  准备就绪")
            self._set_status_property(badge, "idle")
            badge.setToolTip("")
            self._breath_group.stop()
            self._badge_fx.setOpacity(1.0)
        elif self._processing:
            chip.hide()
            badge.setText("●  思考中…")
            self._set_status_property(badge, "processing")
            badge.setToolTip("")
        else:
            chip.hide()
            badge.setText("●  准备就绪")
            self._set_status_property(badge, "idle")
            badge.setToolTip("")

    def _set_processing(self, on: bool):
        if on and self._system_error:
            self._error_btn.blockSignals(True)
            self._error_btn.setChecked(False)
            self._error_btn.blockSignals(False)
            self._system_error = False
        self._processing = on
        if on:
            self._refresh_status_ui()
            self._breath_group.start()
        else:
            self._breath_group.stop()
            self._badge_fx.setOpacity(1.0)
            self._refresh_status_ui()

    def _set_system_error(self, on: bool):
        if on and self._processing:
            self._proc_btn.blockSignals(True)
            self._proc_btn.setChecked(False)
            self._proc_btn.blockSignals(False)
            self._processing = False
            self._breath_group.stop()
            self._badge_fx.setOpacity(1.0)
        self._system_error = on
        self._refresh_status_ui()

    def _on_error_toggled(self, on: bool):
        self._set_system_error(on)

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("ControlPanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel("样式实现控制台")
        title.setObjectName("ControlTitle")
        layout.addWidget(title)

        layout.addWidget(self._section("强调色"))
        self._accent_group = QButtonGroup(self)
        self._accent_radios: dict[str, QRadioButton] = {}
        for idx, (aid, (label, hex_color, _)) in enumerate(ACCENTS.items()):
            if aid.startswith("accent_luxury"):
                continue
            rb = QRadioButton(f"{label}  {hex_color}")
            rb.setProperty("accent_id", aid)
            self._accent_group.addButton(rb, idx)
            self._accent_radios[aid] = rb
            layout.addWidget(rb)
            if aid == DEFAULT_ACCENT:
                rb.setChecked(True)
        self._accent_group.buttonClicked.connect(self._on_accent_changed)

        layout.addWidget(self._section("轻奢对比 A/B/C"))
        self._luxury_group = QButtonGroup(self)
        self._luxury_radios: dict[str, QRadioButton] = {}
        for idx, (preset_id, (label, base_id, accent_id)) in enumerate(
            LUXURY_PRESETS.items()
        ):
            _bhex = BASES.get(base_id, BASES[DEFAULT_BASE])[1]
            _ahex = ACCENTS.get(accent_id, ACCENTS[DEFAULT_ACCENT])[1]
            rb = QRadioButton(f"{label}  ·  {_bhex} + {_ahex}")
            rb.setProperty("luxury_preset_id", preset_id)
            self._luxury_group.addButton(rb, idx)
            self._luxury_radios[preset_id] = rb
            layout.addWidget(rb)
        self._luxury_group.buttonClicked.connect(self._on_luxury_preset_changed)

        layout.addWidget(self._section("轻奢 v2 大改（Demo only）"))
        self._luxury_v2_cb = QCheckBox("启用轻奢 v2 皮肤")
        self._luxury_v2_cb.setObjectName("DemoHint")
        self._luxury_v2_cb.toggled.connect(self._on_luxury_v2_toggled)
        layout.addWidget(self._luxury_v2_cb)

        self._luxury_v2_hint = QLabel(
            "勾选或点击下方任意选项将自动启用 v2；启用后 Crystal/QSS 壳控件暂不可用"
        )
        self._luxury_v2_hint.setObjectName("DemoHint")
        self._luxury_v2_hint.setWordWrap(True)
        layout.addWidget(self._luxury_v2_hint)

        layout.addWidget(QLabel("背景质感"))
        self._luxury_bg_group = QButtonGroup(self)
        for idx, (mode_id, label) in enumerate((("frosted", "磨砂黑"), ("kraft", "牛皮纸黑"))):
            rb = QRadioButton(label)
            rb.setProperty("luxury_bg_mode", mode_id)
            self._luxury_bg_group.addButton(rb, idx)
            layout.addWidget(rb)
            if mode_id == "frosted":
                rb.setChecked(True)
        self._luxury_bg_group.buttonClicked.connect(self._on_luxury_bg_changed)

        layout.addWidget(QLabel("壳层 × 星空"))
        self._luxury_shell_group = QButtonGroup(self)
        for idx, (mode_id, label) in enumerate(
            (("SA", "S-A 半透明磨砂"), ("SB", "S-B 实色纸感卡"), ("SC", "S-C 星空铺满"))
        ):
            rb = QRadioButton(label)
            rb.setProperty("luxury_shell_mode", mode_id)
            self._luxury_shell_group.addButton(rb, idx)
            layout.addWidget(rb)
            if mode_id == "SA":
                rb.setChecked(True)
        self._luxury_shell_group.buttonClicked.connect(self._on_luxury_shell_changed)

        self._luxury_star_label = QLabel()
        self._luxury_star_label.setObjectName("SliderValue")
        self._luxury_star_slider = QSlider(Qt.Horizontal)
        self._luxury_star_slider.setRange(0, 100)
        self._luxury_star_slider.setValue(60)
        self._luxury_star_slider.valueChanged.connect(self._on_luxury_star_changed)
        row_star = QHBoxLayout()
        row_star.addWidget(QLabel("星空强度"))
        row_star.addWidget(self._luxury_star_slider, 1)
        row_star.addWidget(self._luxury_star_label)
        layout.addLayout(row_star)
        self._luxury_star_hint = QLabel("仅磨砂黑显示星空（向下渐隐至 75%）")
        self._luxury_star_hint.setObjectName("DemoHint")
        self._luxury_star_hint.setWordWrap(True)
        layout.addWidget(self._luxury_star_hint)

        layout.addWidget(QLabel("圆角"))
        self._luxury_radius_group = QButtonGroup(self)
        for idx, (rad, label) in enumerate(((10, "10px"), (6, "6px"))):
            rb = QRadioButton(label)
            rb.setProperty("luxury_radius", rad)
            self._luxury_radius_group.addButton(rb, idx)
            layout.addWidget(rb)
            if rad == 10:
                rb.setChecked(True)
        self._luxury_radius_group.buttonClicked.connect(self._on_luxury_radius_changed)

        layout.addWidget(QLabel("顶栏标题（v2）"))
        self._luxury_v2_title_group = QButtonGroup(self)
        for idx, (mode_id, label) in enumerate(LUXURY_V2_TITLE_MODES.items()):
            rb = QRadioButton(label)
            rb.setProperty("luxury_v2_title_mode", mode_id)
            self._luxury_v2_title_group.addButton(rb, idx)
            layout.addWidget(rb)
            if mode_id == DEFAULT_LUXURY_V2_TITLE:
                rb.setChecked(True)
        self._luxury_v2_title_group.buttonClicked.connect(self._on_luxury_v2_title_changed)

        layout.addWidget(QLabel("签名试选（7 款）"))
        self._luxury_script_font_group = QButtonGroup(self)
        for idx, (font_id, label) in enumerate(LUXURY_SCRIPT_FONT_OPTIONS.items()):
            rb = QRadioButton(label)
            rb.setProperty("luxury_script_font_id", font_id)
            self._luxury_script_font_group.addButton(rb, idx)
            layout.addWidget(rb)
            if font_id == DEFAULT_LUXURY_SCRIPT_FONT:
                rb.setChecked(True)
        self._luxury_script_font_group.buttonClicked.connect(self._on_luxury_script_font_changed)

        layout.addWidget(QLabel("鎏金渐变（签名标题）"))
        self._luxury_v2_gold_group = QButtonGroup(self)
        for idx, (mode_id, label) in enumerate(LUXURY_V2_GOLD_MODES.items()):
            rb = QRadioButton(label)
            rb.setProperty("luxury_v2_gold_mode", mode_id)
            self._luxury_v2_gold_group.addButton(rb, idx)
            layout.addWidget(rb)
            if mode_id == DEFAULT_LUXURY_V2_GOLD:
                rb.setChecked(True)
        self._luxury_v2_gold_group.buttonClicked.connect(self._on_luxury_v2_gold_changed)

        layout.addWidget(QLabel("主按钮金边（发送钮 + 示例）"))
        self._luxury_v2_btn_group = QButtonGroup(self)
        for idx, (mode_id, label) in enumerate(LUXURY_V2_BTN_MODES.items()):
            rb = QRadioButton(label)
            rb.setProperty("luxury_v2_btn_mode", mode_id)
            self._luxury_v2_btn_group.addButton(rb, idx)
            layout.addWidget(rb)
            if mode_id == DEFAULT_LUXURY_V2_BTN:
                rb.setChecked(True)
        self._luxury_v2_btn_group.buttonClicked.connect(self._on_luxury_v2_btn_changed)

        self._luxury_btn_edge = QPushButton("示例 · 常驻金边")
        self._luxury_btn_edge.setObjectName("LuxBtnGoldEdge")
        layout.addWidget(self._luxury_btn_edge)
        self._luxury_btn_hover = QPushButton("示例 · hover 金边")
        self._luxury_btn_hover.setObjectName("LuxBtnGoldHover")
        layout.addWidget(self._luxury_btn_hover)

        layout.addWidget(self._section("Shell 模式（三档对比）"))
        self._shell_group = QButtonGroup(self)
        self._shell_radios: dict[str, QRadioButton] = {}
        for idx, (preset_id, label) in enumerate(SHELL_PRESETS.items()):
            rb = QRadioButton(label)
            rb.setProperty("shell_preset", preset_id)
            self._shell_group.addButton(rb, idx)
            self._shell_radios[preset_id] = rb
            layout.addWidget(rb)
            if preset_id == DEFAULT_SHELL_PRESET:
                rb.setChecked(True)
        self._shell_group.buttonClicked.connect(self._on_shell_changed)

        layout.addWidget(self._section("QSS 页面高光"))
        layout.addWidget(QLabel("实底类型"))
        self._qss_body_group = QButtonGroup(self)
        for idx, (mode_id, label) in enumerate(QSS_BODY_MODES.items()):
            rb = QRadioButton(label)
            rb.setProperty("qss_body_mode", mode_id)
            self._qss_body_group.addButton(rb, idx)
            layout.addWidget(rb)
            if mode_id == DEFAULT_QSS_BODY:
                rb.setChecked(True)
        self._qss_body_group.buttonClicked.connect(self._on_qss_body_changed)

        layout.addWidget(QLabel("高光方案"))
        self._qss_highlight_group = QButtonGroup(self)
        for idx, (mode_id, label) in enumerate(QSS_HIGHLIGHT_MODES.items()):
            rb = QRadioButton(label)
            rb.setProperty("qss_highlight_mode", mode_id)
            self._qss_highlight_group.addButton(rb, idx)
            layout.addWidget(rb)
            if mode_id == DEFAULT_QSS_HIGHLIGHT:
                rb.setChecked(True)
        self._qss_highlight_group.buttonClicked.connect(self._on_qss_highlight_changed)

        self._qss_highlight_label = QLabel()
        self._qss_highlight_label.setObjectName("SliderValue")
        self._qss_highlight_slider = QSlider(Qt.Horizontal)
        self._qss_highlight_slider.setRange(0, 60)
        self._qss_highlight_slider.setValue(DEFAULT_QSS_HIGHLIGHT_PEAK)
        self._qss_highlight_slider.valueChanged.connect(self._on_qss_highlight_peak_changed)
        row_qss = QHBoxLayout()
        row_qss.addWidget(QLabel("高光强度"))
        row_qss.addWidget(self._qss_highlight_slider, 1)
        row_qss.addWidget(self._qss_highlight_label)
        layout.addLayout(row_qss)

        self._qss_highlight_hint = QLabel("页面高光需切换为 QSS 实底")
        self._qss_highlight_hint.setObjectName("DemoHint")
        layout.addWidget(self._qss_highlight_hint)

        layout.addWidget(self._section("标题艺术字"))
        self._title_art_group = QButtonGroup(self)
        for idx, (mode_id, label) in enumerate(TITLE_ART_MODES.items()):
            rb = QRadioButton(label)
            rb.setProperty("title_art_mode", mode_id)
            self._title_art_group.addButton(rb, idx)
            layout.addWidget(rb)
            if mode_id == DEFAULT_TITLE_ART:
                rb.setChecked(True)
        self._title_art_group.buttonClicked.connect(self._on_title_art_changed)

        layout.addWidget(self._section("正文字体试验"))
        self._body_font_group = QButtonGroup(self)
        for idx, (font_id, css) in enumerate(BODY_FONT_PRESETS.items()):
            short = font_id.replace("_", " ")
            rb = QRadioButton(f"{short}  ·  {css.split(',')[0].strip('\"')}")
            rb.setProperty("body_font_id", font_id)
            self._body_font_group.addButton(rb, idx)
            layout.addWidget(rb)
            if font_id == DEFAULT_BODY_FONT:
                rb.setChecked(True)
        self._body_font_group.buttonClicked.connect(self._on_body_font_changed)

        layout.addWidget(self._section("Crystal 顶光"))
        self._light_group = QButtonGroup(self)
        for idx, (mode_id, label) in enumerate(LIGHT_MODES.items()):
            rb = QRadioButton(label)
            rb.setProperty("light_mode", mode_id)
            self._light_group.addButton(rb, idx)
            layout.addWidget(rb)
            if mode_id == DEFAULT_LIGHT_MODE:
                rb.setChecked(True)
        self._light_group.buttonClicked.connect(self._on_light_mode_changed)

        self._top_light_label = QLabel()
        self._top_light_label.setObjectName("SliderValue")
        self._top_light_slider = QSlider(Qt.Horizontal)
        self._top_light_slider.setRange(0, 60)
        self._top_light_slider.setValue(DEFAULT_TOP_LIGHT_PEAK)
        self._top_light_slider.valueChanged.connect(self._on_top_light_changed)
        row_tl = QHBoxLayout()
        row_tl.addWidget(QLabel("顶光强度"))
        row_tl.addWidget(self._top_light_slider, 1)
        row_tl.addWidget(self._top_light_label)
        layout.addLayout(row_tl)

        self._top_light_hint = QLabel("顶光试验需切换为 Crystal · 纯细边 / 极轻阴影")
        self._top_light_hint.setObjectName("DemoHint")
        layout.addWidget(self._top_light_hint)

        self._shadow_label = QLabel()
        self._shadow_label.setObjectName("SliderValue")
        self._shadow_slider = QSlider(Qt.Horizontal)
        self._shadow_slider.setRange(0, SHADOW_STRENGTH_MAX)
        self._shadow_slider.setValue(DEFAULT_CRYSTAL_EDGE_SHADOW)
        self._shadow_slider.valueChanged.connect(self._on_crystal_shadow_changed)
        row_sh = QHBoxLayout()
        row_sh.addWidget(QLabel("阴影强度"))
        row_sh.addWidget(self._shadow_slider, 1)
        row_sh.addWidget(self._shadow_label)
        layout.addLayout(row_sh)

        self._shadow_hint = QLabel("阴影试验需切换为 Crystal · 纯细边 / 极轻阴影")
        self._shadow_hint.setObjectName("DemoHint")
        layout.addWidget(self._shadow_hint)

        self._luminance_label = QLabel()
        self._luminance_label.setObjectName("SliderValue")
        self._luminance_slider = QSlider(Qt.Horizontal)
        self._luminance_slider.setRange(50, 150)
        self._luminance_slider.setValue(DEFAULT_SHELL_LUMINANCE)
        self._luminance_slider.valueChanged.connect(self._on_luminance_changed)
        row_lum = QHBoxLayout()
        row_lum.addWidget(QLabel("壳明暗"))
        row_lum.addWidget(self._luminance_slider, 1)
        row_lum.addWidget(self._luminance_label)
        layout.addLayout(row_lum)

        layout.addWidget(self._section("壳底色"))
        self._base_group = QButtonGroup(self)
        self._base_radios: dict[str, QRadioButton] = {}
        for idx, (bid, (label, hex_color, _)) in enumerate(BASES.items()):
            if bid.startswith("base_luxury"):
                continue
            rb = QRadioButton(f"{label}  {hex_color}")
            rb.setProperty("base_id", bid)
            self._base_group.addButton(rb, idx)
            self._base_radios[bid] = rb
            layout.addWidget(rb)
            if bid == DEFAULT_BASE:
                rb.setChecked(True)
        self._base_group.buttonClicked.connect(self._on_base_changed)

        layout.addWidget(self._section("全局字号"))
        font_lbl = QLabel("12px（已定稿）")
        font_lbl.setObjectName("DemoHint")
        layout.addWidget(font_lbl)

        self._medium_alpha_label = QLabel()
        self._medium_alpha_label.setObjectName("SliderValue")
        self._medium_slider = QSlider(Qt.Horizontal)
        self._medium_slider.setRange(80, 95)
        self._medium_slider.setValue(DEFAULT_MEDIUM_ALPHA)
        self._medium_slider.valueChanged.connect(self._on_medium_alpha_changed)
        row_m = QHBoxLayout()
        row_m.addWidget(QLabel("中窗 α"))
        row_m.addWidget(self._medium_slider, 1)
        row_m.addWidget(self._medium_alpha_label)
        layout.addLayout(row_m)

        self._compact_alpha_label = QLabel()
        self._compact_alpha_label.setObjectName("SliderValue")
        self._compact_slider = QSlider(Qt.Horizontal)
        self._compact_slider.setRange(80, 95)
        self._compact_slider.setValue(DEFAULT_COMPACT_ALPHA)
        self._compact_slider.valueChanged.connect(self._on_compact_alpha_changed)
        row_c = QHBoxLayout()
        row_c.addWidget(QLabel("小窗 α"))
        row_c.addWidget(self._compact_slider, 1)
        row_c.addWidget(self._compact_alpha_label)
        layout.addLayout(row_c)

        self._proc_btn = QPushButton("模拟 processing（轻 pulse）")
        self._proc_btn.setObjectName("DemoActionBtn")
        self._proc_btn.setCheckable(True)
        self._proc_btn.toggled.connect(self._set_processing)
        layout.addWidget(self._proc_btn)

        self._error_btn = QPushButton("模拟系统错误（标题行内 Chip + Tooltip）")
        self._error_btn.setObjectName("DemoActionBtn")
        self._error_btn.setCheckable(True)
        self._error_btn.toggled.connect(self._on_error_toggled)
        layout.addWidget(self._error_btn)

        layout.addWidget(self._section("Compact 预览 280×48"))
        compact_wrap = QHBoxLayout()
        compact_wrap.addWidget(self._compact)
        compact_wrap.addStretch()
        layout.addLayout(compact_wrap)

        self._hint = QLabel()
        self._hint.setObjectName("DemoHint")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)
        layout.addStretch()
        self._sync_top_light_controls()
        self._sync_qss_highlight_controls()
        self._sync_shadow_controls()
        self._sync_luxury_v2_controls()
        return panel

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("SectionLabel")
        return lbl

    def _sync_luxury_v2_controls(self) -> None:
        v2_on = self._luxury_v2_enabled
        crystal_shell_disabled = v2_on
        for btn in self._shell_group.buttons():
            btn.setEnabled(not crystal_shell_disabled)
        for btn in self._light_group.buttons():
            btn.setEnabled(not crystal_shell_disabled and _is_crystal_preset(self._shell_preset))
        self._top_light_slider.setEnabled(
            not crystal_shell_disabled and _is_crystal_preset(self._shell_preset)
        )
        for btn in self._qss_body_group.buttons():
            btn.setEnabled(not v2_on and self._shell_preset == "qss")
        for btn in self._qss_highlight_group.buttons():
            btn.setEnabled(not v2_on and self._shell_preset == "qss")
        self._qss_highlight_slider.setEnabled(not v2_on and self._shell_preset == "qss")
        self._shadow_slider.setEnabled(not v2_on and _is_crystal_preset(self._shell_preset))
        for btn in self._title_art_group.buttons():
            btn.setEnabled(not v2_on)
        script_liquid = self._luxury_v2_title_mode == "liquid_script"
        for btn in self._luxury_script_font_group.buttons():
            btn.setEnabled(script_liquid)
        for btn in self._luxury_v2_gold_group.buttons():
            btn.setEnabled(script_liquid)
        frosted_bg = self._luxury_bg_mode == "frosted"
        self._luxury_star_slider.setEnabled(frosted_bg)
        if frosted_bg:
            self._luxury_star_hint.setText("仅磨砂黑显示星空（向下渐隐至 75%）")
        else:
            self._luxury_star_hint.setText("牛皮纸模式无星空，已禁用强度滑杆")
        self._luxury_star_label.setText(str(self._luxury_star_intensity))

    def _ensure_luxury_v2_enabled(self) -> None:
        if self._luxury_v2_enabled:
            return
        self._luxury_v2_enabled = True
        self._luxury_v2_cb.blockSignals(True)
        self._luxury_v2_cb.setChecked(True)
        self._luxury_v2_cb.blockSignals(False)
        self._accent_id = "accent_luxury_a"
        self._base_id = "base_luxury_a"
        self._sync_base_accent_radios()
        self._clear_luxury_selection()
        if "luxury_a" in self._luxury_radios:
            self._luxury_radios["luxury_a"].blockSignals(True)
            self._luxury_radios["luxury_a"].setChecked(True)
            self._luxury_radios["luxury_a"].blockSignals(False)

    def _apply_luxury_shell_props(self) -> None:
        radius = int(self._luxury_radius)
        if self._luxury_shell_mode == "SC":
            radius = min(radius, LUXURY_V2_RADIUS_TIGHT)
        for widget in (self._medium, self._compact):
            widget._luxury_v2_enabled = True
            widget._luxury_bg_mode = self._luxury_bg_mode
            widget._luxury_shell_mode = self._luxury_shell_mode
            widget._luxury_star_intensity = self._luxury_star_intensity
            widget._luxury_radius = radius
            widget.setProperty("_luxury_v2_enabled", True)
            widget.setProperty("_luxury_bg_mode", self._luxury_bg_mode)
            widget.setProperty("_luxury_shell_mode", self._luxury_shell_mode)
            widget.setProperty("_luxury_star_intensity", self._luxury_star_intensity)
            widget.setProperty("_luxury_radius", radius)
            widget._demo_crystal_active = False
            widget._demo_qss_rgba = None
            widget.setGraphicsEffect(None)
            widget.setAutoFillBackground(False)
            widget.setAttribute(Qt.WA_StyledBackground, True)
            widget.setAttribute(Qt.WA_TranslucentBackground, True)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
            widget.repaint()

    def _clear_luxury_shell_props(self) -> None:
        for widget in (self._medium, self._compact):
            widget._luxury_v2_enabled = False
            widget.setProperty("_luxury_v2_enabled", False)

    def _sync_luxury_title(self) -> None:
        script = self._medium.title_script
        if not self._luxury_v2_enabled:
            self._medium.title_restrained.hide()
            self._medium.title_art.show()
            script.hide()
            self._medium.title_art.set_mode(self._title_art_mode)
            alabel, hex_color, _ = _accent_rgb_hex(self._accent_id)
            self._medium.title_art.set_accent(hex_color)
            return
        mode = self._luxury_v2_title_mode
        self._medium.title_restrained.hide()
        self._medium.title_art.hide()
        script.hide()
        script.set_gold_mode(self._luxury_v2_gold_mode)
        if mode == "restrained":
            self._medium.title_restrained.show()
        elif mode == "gradient":
            self._medium.title_art.show()
            self._medium.title_art.set_mode("gradient")
            self._medium.title_art.set_accent(LUX_TOKENS.gold)
        else:
            script.set_font_id(self._luxury_script_font_id)
            script.show()
        self._medium.title_restrained.update()
        self._medium.title_art.update()
        script.update()

    def _sync_luxury_icons(self) -> None:
        if not self._luxury_v2_enabled:
            self._medium.menu_btn.setText("☰")
            self._medium.menu_btn.setIcon(QIcon())
            self._medium.mic_btn.setIcon(action_icon("mic"))
            self._medium.send_btn.setText("➤")
            self._medium.send_btn.setIcon(QIcon())
            self._medium.send_btn.setObjectName("SendBtnAccent")
            for btn in (self._medium.menu_btn, self._medium.mic_btn, self._medium.send_btn):
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            return
        self._medium.menu_btn.setText("")
        self._medium.menu_btn.setIcon(luxury_icon("menu", 20))
        self._medium.mic_btn.setIcon(luxury_icon("mic", 18))
        self._medium.send_btn.setText("")
        self._medium.send_btn.setIcon(luxury_icon("send", 18))
        edge = self._luxury_v2_btn_mode == "edge"
        name = "SendBtnLuxEdge" if edge else "SendBtnLuxHover"
        self._medium.send_btn.setObjectName(name)
        for btn in (self._medium.menu_btn, self._medium.mic_btn, self._medium.send_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_luxury_v2_toggled(self, on: bool) -> None:
        self._luxury_v2_enabled = on
        if on:
            self._accent_id = "accent_luxury_a"
            self._base_id = "base_luxury_a"
            self._sync_base_accent_radios()
            self._clear_luxury_selection()
            if "luxury_a" in self._luxury_radios:
                self._luxury_radios["luxury_a"].blockSignals(True)
                self._luxury_radios["luxury_a"].setChecked(True)
                self._luxury_radios["luxury_a"].blockSignals(False)
        self._apply_preview()

    def _on_luxury_bg_changed(self, button: QRadioButton) -> None:
        self._ensure_luxury_v2_enabled()
        self._luxury_bg_mode = button.property("luxury_bg_mode") or "frosted"
        self._apply_preview()

    def _on_luxury_shell_changed(self, button: QRadioButton) -> None:
        self._ensure_luxury_v2_enabled()
        mode = button.property("luxury_shell_mode") or "SA"
        self._luxury_shell_mode = mode
        if mode == "SC":
            self._luxury_radius = LUXURY_V2_RADIUS_TIGHT
            for btn in self._luxury_radius_group.buttons():
                rad = btn.property("luxury_radius")
                if rad is not None and int(rad) == LUXURY_V2_RADIUS_TIGHT:
                    btn.setChecked(True)
                    break
        self._apply_preview()

    def _on_luxury_star_changed(self, value: int) -> None:
        self._ensure_luxury_v2_enabled()
        self._luxury_star_intensity = value
        self._apply_preview()

    def _on_luxury_radius_changed(self, button: QRadioButton) -> None:
        self._ensure_luxury_v2_enabled()
        self._luxury_radius = int(button.property("luxury_radius") or LUXURY_V2_RADIUS_DEFAULT)
        self._apply_preview()

    def _on_luxury_v2_title_changed(self, button: QRadioButton) -> None:
        self._ensure_luxury_v2_enabled()
        self._luxury_v2_title_mode = button.property("luxury_v2_title_mode") or DEFAULT_LUXURY_V2_TITLE
        self._apply_preview()

    def _on_luxury_script_font_changed(self, button: QRadioButton) -> None:
        self._ensure_luxury_v2_enabled()
        self._luxury_script_font_id = (
            button.property("luxury_script_font_id") or DEFAULT_LUXURY_SCRIPT_FONT
        )
        self._luxury_v2_title_mode = "liquid_script"
        for btn in self._luxury_v2_title_group.buttons():
            if btn.property("luxury_v2_title_mode") == "liquid_script":
                btn.blockSignals(True)
                btn.setChecked(True)
                btn.blockSignals(False)
                break
        self._apply_preview()

    def _on_luxury_v2_gold_changed(self, button: QRadioButton) -> None:
        self._ensure_luxury_v2_enabled()
        self._luxury_v2_gold_mode = button.property("luxury_v2_gold_mode") or DEFAULT_LUXURY_V2_GOLD
        self._apply_preview()

    def _on_luxury_v2_btn_changed(self, button: QRadioButton) -> None:
        self._ensure_luxury_v2_enabled()
        self._luxury_v2_btn_mode = button.property("luxury_v2_btn_mode") or DEFAULT_LUXURY_V2_BTN
        self._apply_preview()

    def _clear_luxury_selection(self) -> None:
        self._luxury_group.setExclusive(False)
        for rb in self._luxury_radios.values():
            rb.setChecked(False)
        self._luxury_group.setExclusive(True)

    def _sync_base_accent_radios(self) -> None:
        for bid, rb in getattr(self, "_base_radios", {}).items():
            rb.blockSignals(True)
            rb.setChecked(bid == self._base_id)
            rb.blockSignals(False)
        for aid, rb in getattr(self, "_accent_radios", {}).items():
            rb.blockSignals(True)
            rb.setChecked(aid == self._accent_id)
            rb.blockSignals(False)

    def _on_accent_changed(self, button: QRadioButton):
        self._clear_luxury_selection()
        self._accent_id = button.property("accent_id") or DEFAULT_ACCENT
        self._apply_preview()

    def _on_luxury_preset_changed(self, button: QRadioButton):
        preset_id = button.property("luxury_preset_id")
        if not preset_id or preset_id not in LUXURY_PRESETS:
            return
        _label, base_id, accent_id = LUXURY_PRESETS[preset_id]
        self._base_id = base_id
        self._accent_id = accent_id
        self._sync_base_accent_radios()
        self._apply_preview()

    def _on_base_changed(self, button: QRadioButton):
        self._clear_luxury_selection()
        self._base_id = button.property("base_id") or DEFAULT_BASE
        self._apply_preview()

    def _on_shell_changed(self, button: QRadioButton):
        new_preset = button.property("shell_preset") or DEFAULT_SHELL_PRESET
        if new_preset != self._shell_preset and _is_crystal_preset(new_preset):
            strength = default_crystal_shadow_strength(new_preset)
            self._crystal_shadow_strength = strength
            self._shadow_slider.blockSignals(True)
            self._shadow_slider.setValue(strength)
            self._shadow_slider.blockSignals(False)
        self._shell_preset = new_preset
        self._apply_preview()

    def _on_crystal_shadow_changed(self, value: int):
        self._crystal_shadow_strength = value
        if not self._apply_crystal_shadow_only():
            self._update_hint_labels()

    def _on_qss_body_changed(self, button: QRadioButton):
        mode = button.property("qss_body_mode") or DEFAULT_QSS_BODY
        self._qss_body_mode = mode  # type: ignore[assignment]
        if not self._apply_qss_highlight_only():
            self._update_hint_labels()

    def _on_qss_highlight_changed(self, button: QRadioButton):
        mode = button.property("qss_highlight_mode") or DEFAULT_QSS_HIGHLIGHT
        self._qss_highlight_mode = mode  # type: ignore[assignment]
        if not self._apply_qss_highlight_only():
            self._update_hint_labels()

    def _on_qss_highlight_peak_changed(self, value: int):
        self._qss_highlight_peak = value
        if not self._apply_qss_highlight_only():
            self._update_hint_labels()

    def _on_title_art_changed(self, button: QRadioButton):
        self._title_art_mode = button.property("title_art_mode") or DEFAULT_TITLE_ART
        self._apply_preview()

    def _on_body_font_changed(self, button: QRadioButton):
        self._body_font_id = button.property("body_font_id") or DEFAULT_BODY_FONT
        self._apply_preview()

    def _on_light_mode_changed(self, button: QRadioButton):
        mode = button.property("light_mode") or DEFAULT_LIGHT_MODE
        self._light_mode = mode  # type: ignore[assignment]
        if not self._apply_crystal_light_only():
            self._update_hint_labels()

    def _on_top_light_changed(self, value: int):
        self._top_light_peak = value
        if not self._apply_crystal_light_only():
            self._update_hint_labels()

    def _on_luminance_changed(self, value: int):
        self._shell_luminance = value
        self._apply_preview()

    def _on_medium_alpha_changed(self, value: int):
        self._medium_alpha = value
        self._apply_preview()

    def _on_compact_alpha_changed(self, value: int):
        self._compact_alpha = value
        self._apply_preview()

    def _apply_preview(self):
        app = QApplication.instance()
        if self._luxury_v2_enabled:
            self._apply_luxury_shell_props()
            qss = compose_luxury_v2_qss(
                self._font_size,
                self._body_font_id,
                shell_radius=int(self._luxury_radius),
                send_btn_style=self._luxury_v2_btn_mode,
            )
            app.setStyleSheet(qss)
            self._sync_luxury_title()
            self._sync_luxury_icons()
        else:
            self._clear_luxury_shell_props()
            preset = self._shell_preset
            qss = compose_demo_qss(
                self._accent_id,
                preset,
                self._base_id,
                self._medium_alpha,
                self._compact_alpha,
                self._font_size,
                body_font_id=self._body_font_id,
                shell_luminance=self._shell_luminance,
            )
            app.setStyleSheet(qss)
            tokens = self._compute_tokens()
            self._apply_shell_from_tokens(tokens)
            alabel, hex_color, _ = _accent_rgb_hex(self._accent_id)
            self._medium.title_art.set_accent(hex_color)
            self._medium.title_art.set_mode(self._title_art_mode)
            self._sync_luxury_title()
            self._sync_luxury_icons()

        self._sync_top_light_controls()
        self._sync_qss_highlight_controls()
        self._sync_shadow_controls()
        self._sync_luxury_v2_controls()
        self._refresh_left_preview()

        if self._processing:
            self._refresh_status_ui()
            self._breath_group.start()
        elif self._system_error:
            self._refresh_status_ui()

        self._update_hint_labels()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    apply_app_font(app)
    win = StylePreviewWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
