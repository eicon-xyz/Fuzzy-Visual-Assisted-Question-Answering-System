"""Top bar layout builder — structure only, zero styling."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
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
from ui.native.widgets import MenuButton


@dataclass
class TopBarLayoutResult:
    bar: QWidget
    menu_btn: MenuButton
    title_art: TitleArtWidget
    panel_sub: QLabel
    error_chip: QLabel
    mode_pills: QWidget
    mode_pill_labels: List[QLabel]
    status_badge: QLabel


def build_topbar(parent: QWidget | None = None) -> TopBarLayoutResult:
    """Create top bar widget tree + objectNames; no colors or fonts."""
    bar = QWidget(parent)
    bar.setObjectName("TopBar")
    bar.setMinimumHeight(TOP_BAR_MIN_H)
    bar.setMaximumHeight(TOP_BAR_MAX_H)

    layout = QHBoxLayout(bar)
    layout.setContentsMargins(
        TOP_BAR_PAD_H, TOP_BAR_PAD_V, TOP_BAR_PAD_H, TOP_BAR_PAD_V
    )
    layout.setSpacing(TOP_BAR_SPACING)

    menu_btn = MenuButton(bar)
    menu_btn.setFixedSize(34, 34)
    menu_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    layout.addWidget(menu_btn)

    text_wrap = QWidget(bar)
    text_wrap.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    text_row = QHBoxLayout(text_wrap)
    text_row.setContentsMargins(0, 0, 0, 0)
    text_row.setSpacing(TOP_BAR_TITLE_GAP)
    title_art = TitleArtWidget(text_wrap)
    text_row.addWidget(title_art)
    title_sep = QLabel("·", text_wrap)
    title_sep.setObjectName("TopTitleSep")
    title_sep.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    text_row.addWidget(title_sep)
    panel_sub = QLabel("操作指引", text_wrap)
    panel_sub.setObjectName("TopSub")
    panel_sub.setMinimumWidth(0)
    panel_sub.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    text_row.addWidget(panel_sub)
    layout.addWidget(text_wrap)

    layout.addStretch(1)

    error_chip = QLabel("● A端连接失败", bar)
    error_chip.setObjectName("TopErrorChip")
    error_chip.hide()
    layout.addWidget(error_chip)

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
        panel_sub=panel_sub,
        error_chip=error_chip,
        mode_pills=mode_pills,
        mode_pill_labels=mode_pill_labels,
        status_badge=status_badge,
    )
