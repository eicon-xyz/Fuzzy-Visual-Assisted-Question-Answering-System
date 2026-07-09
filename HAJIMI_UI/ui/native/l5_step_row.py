# -*- coding: utf-8 -*-
"""L5 单步行：复用 StepCard + 可选截图条 + 执行日志。"""
from __future__ import annotations

import base64
from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.step_list import StepCard

THUMB_W = 160
THUMB_H = 90

_LEVEL_PREFIX = {
    "info": "·",
    "debug": "·",
    "warn": "⚠",
    "error": "✗",
}


def decode_screenshot_b64(b64: str) -> Optional[QPixmap]:
    if not b64:
        return None
    try:
        raw = b64.split(",", 1)[-1]
        img_data = base64.b64decode(raw)
        pix = QPixmap()
        if pix.loadFromData(img_data):
            return pix
    except Exception:
        pass
    return None


class L5StepRow(QWidget):
    """一步：StepCard + 截图缩略图条（无图不占位）+ 可折叠日志。"""

    def __init__(
        self,
        index: int,
        instruction: str,
        *,
        preview_factory: Optional[Callable[[QPixmap], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._index = index
        self._instruction = instruction
        self._preview_factory = preview_factory
        self._screenshot_count = 0
        self.setObjectName("L5StepRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._card = StepCard(index, instruction)
        root.addWidget(self._card)

        self._shot_frame = QFrame()
        self._shot_frame.setObjectName("L5ShotStrip")
        self._shot_frame.hide()
        shot_outer = QHBoxLayout(self._shot_frame)
        shot_outer.setContentsMargins(12, 0, 12, 0)
        self._shot_scroll = QScrollArea()
        self._shot_scroll.setObjectName("L5ShotScroll")
        self._shot_scroll.setWidgetResizable(True)
        self._shot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._shot_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._shot_scroll.setFixedHeight(THUMB_H + 8)
        self._shot_inner = QWidget()
        self._shot_layout = QHBoxLayout(self._shot_inner)
        self._shot_layout.setContentsMargins(0, 0, 0, 0)
        self._shot_layout.setSpacing(8)
        self._shot_scroll.setWidget(self._shot_inner)
        shot_outer.addWidget(self._shot_scroll)
        root.addWidget(self._shot_frame)

        self._log_frame = QFrame()
        self._log_frame.setObjectName("L5StepLog")
        self._log_frame.hide()
        log_layout = QVBoxLayout(self._log_frame)
        log_layout.setContentsMargins(12, 0, 12, 4)
        self._log_area = QPlainTextEdit()
        self._log_area.setObjectName("L5StepLogText")
        self._log_area.setReadOnly(True)
        self._log_area.setMaximumBlockCount(200)
        self._log_area.setFixedHeight(72)
        self._log_area.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        log_layout.addWidget(self._log_area)
        root.addWidget(self._log_frame)

    @property
    def index(self) -> int:
        return self._index

    @property
    def instruction(self) -> str:
        return self._instruction

    @property
    def screenshot_count(self) -> int:
        return self._screenshot_count

    def set_status(self, status: str) -> None:
        self._card.set_status(status)

    def set_expanded(self, expanded: bool) -> None:
        self._log_frame.setVisible(expanded and bool(self._log_area.toPlainText()))

    def append_log(self, text: str, *, kind: str = "info") -> None:
        if not text:
            return
        prefix = _LEVEL_PREFIX.get(kind, "·")
        line = f"{prefix} {text}"
        existing = self._log_area.toPlainText()
        if existing:
            self._log_area.appendPlainText(line)
        else:
            self._log_area.setPlainText(line)
        self._log_frame.show()

    def add_screenshot(self, b64: str) -> bool:
        pix = decode_screenshot_b64(b64)
        if pix is None:
            return False
        thumb = pix.scaled(
            THUMB_W,
            THUMB_H,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        label = QLabel()
        label.setObjectName("L5ShotThumb")
        label.setPixmap(thumb)
        label.setCursor(Qt.PointingHandCursor)
        label.setToolTip("点击放大")
        full_pix = pix

        def _on_click(_ev, p=full_pix):
            if self._preview_factory:
                self._preview_factory(p)

        label.mousePressEvent = _on_click  # type: ignore[method-assign]
        self._shot_layout.addWidget(label)
        self._screenshot_count += 1
        self._shot_frame.show()
        return True

    def mark_all_done_if_pending(self) -> None:
        if self._card.status in ("pending", "active"):
            self.set_status("done")
