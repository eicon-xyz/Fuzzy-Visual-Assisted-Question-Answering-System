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
from ui.native.widgets import MenuButton


@dataclass
class TopBarLayoutResult:
    bar: QWidget
    menu_btn: MenuButton
    panel_sub: QLabel
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
    layout.addWidget(menu_btn)

    text_wrap = QWidget(bar)
    text_wrap.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    text_col = QVBoxLayout(text_wrap)
    text_col.setContentsMargins(0, 0, 0, 0)
    text_col.setSpacing(TOP_BAR_TITLE_GAP)
    title = QLabel("HAJIMI", text_wrap)
    title.setObjectName("TopTitle")
    title.setMinimumWidth(0)
    title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    panel_sub = QLabel("操作指引", text_wrap)
    panel_sub.setObjectName("TopSub")
    panel_sub.setMinimumWidth(0)
    panel_sub.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    text_col.addWidget(title)
    text_col.addWidget(panel_sub)
    layout.addWidget(text_wrap)

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
        panel_sub=panel_sub,
        mode_pills=mode_pills,
        mode_pill_labels=mode_pill_labels,
        status_badge=status_badge,
    )
