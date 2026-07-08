"""Luxury theme QSS composer for production main.py."""
from __future__ import annotations

from ui.native.layout_tokens import FONT_FAMILY, FONT_FAMILY_FALLBACK
from ui.native.luxury.paint import TOKENS

LUXURY_SHELL_RADIUS = 10
LUXURY_COMPACT_RADIUS = 26

LUXURY_BG_MODES = {"frosted": "磨砂黑", "kraft": "牛皮纸黑"}
LUXURY_BTN_MODES = ("edge", "hover")
DEFAULT_LUXURY_BTN_MODE = "hover"
DEFAULT_LUXURY_GOLD_MODE = "dual_layer"


def compose_luxury_stylesheet(
    font_size: int,
    *,
    shell_radius: int = LUXURY_SHELL_RADIUS,
    compact_radius: int = LUXURY_COMPACT_RADIUS,
    send_btn_style: str = DEFAULT_LUXURY_BTN_MODE,
) -> str:
    body_font = f'"{FONT_FAMILY}", "{FONT_FAMILY_FALLBACK}", "PingFang SC", sans-serif'
    bubble_label = font_size + 1
    gold = TOKENS.gold
    hover_border = "rgba(201, 168, 76, 0.25)"
    return f"""
* {{
    font-family: {body_font};
    font-size: {font_size}px;
    color: {TOKENS.secondary};
}}
QWidget#NativeShell {{
    background: transparent;
    background-color: transparent;
    border: none;
    border-radius: {shell_radius}px;
}}
QWidget#CompactShell {{
    background: transparent;
    background-color: transparent;
    border: none;
    border-radius: {compact_radius}px;
}}
QWidget#TopBar {{
    background: transparent;
    border-bottom: 1px solid {TOKENS.surface_line};
}}
QWidget#TitleArt, QWidget#LuxuryScriptTitle {{
    background: transparent;
}}
QLabel#TopSub {{
    font-size: 12px;
    color: {TOKENS.secondary_muted};
    font-weight: 500;
}}
QLabel#TopTitleSep {{
    font-size: 12px;
    color: {TOKENS.secondary_muted};
    padding: 0 2px;
}}
QLabel#TopErrorChip {{
    font-size: 11px;
    font-weight: 600;
    color: #e74c3c;
}}
QLabel#StatusBadge[status="error"] {{
    background: rgba(231, 76, 60, 0.12);
    color: #e74c3c;
    border: none;
}}
QLabel#StatusBadge {{
    padding: 6px 16px;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 600;
    background: rgba(255, 255, 255, 0.05);
    color: {TOKENS.secondary_muted};
    border: none;
}}
QLabel#StatusBadge[status="processing"] {{
    background: rgba(201, 168, 76, 0.12);
    color: {gold};
}}
QPushButton#MenuBtn, QPushButton#LuxIconBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    min-width: 34px;
    min-height: 34px;
    color: {TOKENS.secondary_muted};
    font-size: 16px;
}}
QPushButton#MenuBtn:hover, QPushButton#LuxIconBtn:hover {{
    background: rgba(255, 255, 255, 0.05);
}}
QScrollArea#MediumContent,
QScrollArea#SettingsScroll {{
    background: transparent;
    border: none;
}}
QScrollArea#MediumContent QAbstractScrollArea::viewport,
QScrollArea#SettingsScroll QAbstractScrollArea::viewport {{
    background: transparent;
    border: none;
}}
QWidget#MediumContentWrap,
QStackedWidget#MediumPages,
QWidget#MediumPage,
QWidget#MediumChatContainer,
QWidget#ChatBubbleHost,
QWidget#SettingsScrollInner,
QWidget#InputDock {{
    background: transparent;
    border: none;
}}
QFrame#bubble-user {{
    background-color: #1C1916;
    border: 1px solid {TOKENS.surface_line};
    border-radius: 10px;
    border-top-right-radius: 2px;
}}
QFrame#bubble-system {{
    background-color: {TOKENS.bg_elevated};
    border: 1px solid {TOKENS.surface_line};
    border-radius: 10px;
    border-top-left-radius: 2px;
}}
QLabel#bubbleUserLabel, QLabel#bubbleSystemLabel {{
    color: {TOKENS.secondary};
    font-size: {bubble_label}px;
}}
QFrame#InputFloat {{
    background: {TOKENS.bg_elevated};
    border: 1px solid {TOKENS.surface_line};
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
    color: {TOKENS.secondary};
    font-size: {font_size}px;
}}
QPushButton#LuxBtnGoldEdge, QPushButton#SendBtnLuxEdge {{
    background: {TOKENS.bg_elevated};
    border: 1px solid {gold};
    border-radius: 8px;
    color: {TOKENS.secondary};
    font-size: 14px;
    min-width: 32px;
    min-height: 32px;
}}
QPushButton#LuxBtnGoldHover, QPushButton#SendBtnLuxHover {{
    background: {TOKENS.bg_elevated};
    border: 1px solid {hover_border};
    border-radius: 8px;
    color: {TOKENS.secondary};
    font-size: 14px;
    min-width: 32px;
    min-height: 32px;
}}
QPushButton#LuxBtnGoldHover:hover, QPushButton#SendBtnLuxHover:hover {{
    border: 1px solid {gold};
    background: rgba(201, 168, 76, 0.08);
}}
QPushButton#StepBtnPrimary {{
    background: {TOKENS.bg_elevated};
    border: 1px solid {hover_border};
    border-radius: 8px;
    color: {TOKENS.secondary};
    font-weight: 600;
    padding: 8px 16px;
}}
QPushButton#StepBtnPrimary:hover {{
    border: 1px solid {gold};
    background: rgba(201, 168, 76, 0.08);
}}
QPushButton#StepBtn {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid {TOKENS.surface_line};
    border-radius: 8px;
    color: {TOKENS.secondary_muted};
    padding: 8px 16px;
}}
QPushButton#StepBtn:hover {{
    background: rgba(255, 255, 255, 0.06);
    color: {TOKENS.secondary};
}}
QFrame#Card {{
    background: rgba(20, 18, 16, 0.72);
    border: 1px solid {TOKENS.surface_line};
    border-radius: 16px;
}}
QLabel#SectionTitle, QLabel#HintText, QLabel#HintTextSmall {{
    color: {TOKENS.secondary_muted};
    background: transparent;
}}
QLabel#CardTitle {{
    color: {TOKENS.secondary_muted};
}}
QRadioButton#SettingsRadio {{
    color: {TOKENS.secondary};
    spacing: 8px;
}}
QPushButton#CollapseToggle {{
    background: transparent;
    border: none;
    color: {TOKENS.secondary_muted};
    text-align: left;
    padding: 4px 0;
}}
QPushButton#CollapseToggle:hover {{
    color: {TOKENS.secondary};
}}
QLabel#CompactMark {{
    background: rgba(201, 168, 76, 0.12);
    border: 1px solid rgba(201, 168, 76, 0.25);
    border-radius: 10px;
    color: {gold};
    font-size: 15px;
}}
QLineEdit#CompactInput {{
    background: transparent;
    border: none;
    color: {TOKENS.secondary};
}}
QLabel#CompactHint {{
    color: {TOKENS.secondary_muted};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 4px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.08);
    border-radius: 4px;
}}
QWidget#NavBackdrop {{
    background: rgba(0, 0, 0, 0.55);
}}
QWidget#NavDrawer {{
    background: rgba(20, 18, 16, 0.92);
    border-right: 1px solid {TOKENS.surface_line};
}}
QLabel#DrawerHead {{
    color: {TOKENS.secondary};
    font-size: 12px;
    font-weight: 600;
}}
QFrame#DrawerSep {{
    background: {TOKENS.surface_line};
    max-height: 1px;
}}
QPushButton#NavItem {{
    text-align: left;
    padding: 9px 10px;
    border: none;
    border-radius: 10px;
    color: {TOKENS.secondary_muted};
    background: transparent;
    font-size: 12px;
}}
QPushButton#NavItem:hover {{
    background: rgba(255, 255, 255, 0.04);
    color: {TOKENS.secondary};
}}
QPushButton#NavItem[active="true"] {{
    color: {gold};
    background: transparent;
    border: none;
}}
QPushButton#NavItemQuit {{
    text-align: left;
    padding: 9px 10px;
    border: none;
    border-radius: 10px;
    color: {TOKENS.secondary_muted};
    background: transparent;
    font-size: 12px;
    margin-top: 4px;
}}
QPushButton#NavItemQuit:hover {{
    background: rgba(255, 255, 255, 0.04);
    color: {TOKENS.secondary};
}}
"""
