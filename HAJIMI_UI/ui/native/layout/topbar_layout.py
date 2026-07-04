"""Top bar layout builder — structure only, zero styling."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
)

from ui.native.layout_tokens import (
    TOP_BAR_MIN_H,
    TOP_BAR_MAX_H,
    TOP_BAR_PAD_H,
    TOP_BAR_PAD_V,
    TOP_BAR_SPACING,
    TOP_BAR_TITLE_GAP,
)
from ui.native.title_art import TitleArtWidget
from ui.native.luxury.title import LuxuryScriptTitleWidget
from ui.native.widgets import MenuButton

_BADGE_LABELS = ("准备就绪", "A端不可达", "AI 思考中...", "正在指引中", "异常挂起", "已终止", "已结束")
_MENU_BTN_W = 34
_EXTRA_MARGIN = 12


@dataclass
class TopBarLayoutResult:
    bar: QWidget
    menu_btn: MenuButton
    title_art: TitleArtWidget
    title_script: LuxuryScriptTitleWidget
    title_sep: QLabel
    panel_sub: QLabel
    mode_pills: QWidget
    mode_pill_labels: List[QLabel]
    status_badge: QLabel


def compute_topbar_min_width(
    title_widget: QWidget,
    panel_sub: QLabel,
    status_badge: QLabel,
    *,
    include_panel_sub: bool = True,
    title_sep: QLabel | None = None,
    badge_labels: Sequence[str] = _BADGE_LABELS,
) -> int:
    """Minimum window width for top bar chrome (menu + title + badge [+ panel sub])."""
    pad = TOP_BAR_PAD_H * 2
    menu = _MENU_BTN_W
    spacing = TOP_BAR_SPACING * 2
    title_w = title_widget.sizeHint().width()
    sub_w = 0
    if include_panel_sub:
        if title_sep is not None:
            sub_w += title_sep.sizeHint().width() + TOP_BAR_TITLE_GAP
        panel_sub.ensurePolished()
        fm = QFontMetrics(panel_sub.font())
        sub_w += fm.horizontalAdvance(panel_sub.text()) + TOP_BAR_TITLE_GAP
    badge_font = status_badge.font()
    bfm = QFontMetrics(badge_font)
    badge_text_w = max(bfm.horizontalAdvance(f"● {label}") for label in badge_labels)
    badge_pad = 32
    return pad + menu + spacing + title_w + sub_w + badge_text_w + badge_pad + _EXTRA_MARGIN


def build_topbar(parent: QWidget | None = None) -> TopBarLayoutResult:
    """Create top bar widget tree + objectNames; no colors or fonts."""
    bar = QWidget(parent)
    bar.setObjectName("TopBar")
    bar.setMinimumHeight(TOP_BAR_MIN_H)
    bar.setMaximumHeight(TOP_BAR_MAX_H)
    bar.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

    layout = QHBoxLayout(bar)
    layout.setContentsMargins(
        TOP_BAR_PAD_H, TOP_BAR_PAD_V, TOP_BAR_PAD_H, TOP_BAR_PAD_V
    )
    layout.setSpacing(TOP_BAR_SPACING)

    menu_btn = MenuButton(bar)
    menu_btn.setFixedSize(_MENU_BTN_W, _MENU_BTN_W)
    menu_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    layout.addWidget(menu_btn)

    text_wrap = QWidget(bar)
    text_wrap.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    text_row = QHBoxLayout(text_wrap)
    text_row.setContentsMargins(0, 0, 0, 0)
    text_row.setSpacing(TOP_BAR_TITLE_GAP)
    title_art = TitleArtWidget(text_wrap)
    title_art.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    text_row.addWidget(title_art)
    title_script = LuxuryScriptTitleWidget(text_wrap)
    title_script.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    title_script.hide()
    text_row.addWidget(title_script)
    title_sep = QLabel("·", text_wrap)
    title_sep.setObjectName("TopTitleSep")
    title_sep.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    text_row.addWidget(title_sep)
    panel_sub = QLabel("操作指引", text_wrap)
    panel_sub.setObjectName("TopSub")
    panel_sub.setMinimumWidth(0)
    panel_sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    text_row.addWidget(panel_sub)
    layout.addWidget(text_wrap, 0)

    layout.addStretch(1)

    right_wrap = QWidget(bar)
    right_wrap.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    right_l = QHBoxLayout(right_wrap)
    right_l.setContentsMargins(0, 0, 0, 0)
    right_l.setSpacing(12)

    mode_pills = QWidget(right_wrap)
    mode_pills.setObjectName("ModePills")
    mode_pills.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    pl = QHBoxLayout(mode_pills)
    pl.setContentsMargins(0, 0, 0, 0)
    pl.setSpacing(8)
    mode_pill_labels: List[QLabel] = []
    for label, active in (("L1", False), ("L2", False), ("L3", True)):
        pill = QLabel(label, mode_pills)
        pill.setObjectName("ModePill")
        pill.setProperty("active", "true" if active else "false")
        pl.addWidget(pill)
        mode_pill_labels.append(pill)
    right_l.addWidget(mode_pills)
    mode_pills.hide()

    status_badge = QLabel("● 准备就绪", right_wrap)
    status_badge.setObjectName("StatusBadge")
    status_badge.setProperty("status", "idle")
    status_badge.setMinimumWidth(0)
    status_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    right_l.addWidget(status_badge)
    layout.addWidget(right_wrap)

    return TopBarLayoutResult(
        bar=bar,
        menu_btn=menu_btn,
        title_art=title_art,
        title_script=title_script,
        title_sep=title_sep,
        panel_sub=panel_sub,
        mode_pills=mode_pills,
        mode_pill_labels=mode_pill_labels,
        status_badge=status_badge,
    )
