# -*- coding: utf-8 -*-
"""L5 自动执行 — 规划步骤 + 可折叠执行时间线。"""
from __future__ import annotations

import base64
import os
from typing import Optional

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

THUMB_W = 160
THUMB_H = 90

_STATUS_DOT = {
    "pending": "○",
    "active": "●",
    "done": "✓",
    "failed": "✗",
    "blocked": "⊘",
}

_LEVEL_DOT = {
    "info": "·",
    "debug": "·",
    "warn": "⚠",
    "error": "✗",
}


def l5_tool_sse_enabled() -> bool:
    try:
        from config import L5_TOOL_SSE

        return bool(L5_TOOL_SSE)
    except Exception:
        return os.environ.get("HAJIMI_L5_TOOL_SSE", "0").strip() in ("1", "true", "yes")


class _ScreenshotPreviewDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("L5 截屏预览")
        layout = QVBoxLayout(self)
        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignCenter)
        scroll = QScrollArea()
        scroll.setWidget(label)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        self.resize(min(960, pixmap.width() + 40), min(720, pixmap.height() + 40))


class L5StepTimelineWidget(QWidget):
    """双层结构：规划步骤（顶层）+ 每步执行时间线（子节点）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step_items: list[QTreeWidgetItem] = []
        self._active_index = -1
        self._total_steps = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)

        hint = QLabel("执行时间线（当前步自动展开）")
        hint.setObjectName("HintTextSmall")
        layout.addWidget(hint)

        self._tree = QTreeWidget()
        self._tree.setObjectName("L5TimelineTree")
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(True)
        layout.addWidget(self._tree, 1)

    def reset_plan(self, steps: list) -> None:
        self._tree.clear()
        self._step_items.clear()
        self._active_index = -1
        self._total_steps = len(steps)
        for i, step in enumerate(steps):
            if isinstance(step, dict):
                text = (
                    step.get("instruction")
                    or step.get("description")
                    or step.get("desc")
                    or f"步骤 {i + 1}"
                )
            else:
                text = str(step)
            item = QTreeWidgetItem([f"○ {i + 1}. {text}"])
            item.setData(0, Qt.UserRole, i)
            self._tree.addTopLevelItem(item)
            self._step_items.append(item)
        self._tree.expandAll()
        for item in self._step_items:
            item.setExpanded(False)

    def set_step_status(self, index: int, status: str) -> None:
        if index < 0 or index >= len(self._step_items):
            return
        item = self._step_items[index]
        dot = _STATUS_DOT.get(status, "○")
        label = item.text(0)
        if ". " in label:
            rest = label.split(". ", 1)[1]
        else:
            rest = label.lstrip("○●✓✗⊘ ").lstrip("0123456789. ")
        item.setText(0, f"{dot} {index + 1}. {rest}")

    def handle_sse(self, event_type: str, data: dict) -> None:
        step_index = int(data.get("step_index", 1)) - 1
        if event_type == "step_start":
            self._set_active_step(step_index)
            self.set_step_status(step_index, "active")
            self._append_line(
                step_index,
                f"● 开始执行",
                kind="info",
            )
        elif event_type == "log":
            level = str(data.get("level", "info"))
            msg = str(data.get("message", ""))
            if msg:
                self._append_line(step_index, msg, kind=level)
        elif event_type == "screenshot_updated":
            b64 = data.get("annotated_image") or data.get("image_base64") or ""
            if b64:
                self._append_screenshot(step_index, b64)
        elif event_type == "step_done":
            summary = str(data.get("action_summary") or "完成")
            self.set_step_status(step_index, "done")
            self._append_line(step_index, f"✓ {summary}", kind="info")
        elif event_type == "step_failed":
            reason = str(data.get("reason") or data.get("error") or "失败")
            self.set_step_status(step_index, "failed")
            self._append_line(step_index, f"✗ {reason}", kind="error")
        elif event_type == "step_blocked":
            self.set_step_status(step_index, "blocked")
            msg = str(data.get("message") or data.get("reason") or "需批准")
            self._append_line(step_index, f"⊘ {msg}", kind="warn")
        elif event_type == "tool_called" and l5_tool_sse_enabled():
            tool = data.get("tool", "?")
            args = data.get("args") or data.get("params") or {}
            brief = ", ".join(f"{k}={v}" for k, v in list(args.items())[:3])
            self._append_line(
                step_index,
                f"→ {tool}({brief})" if brief else f"→ {tool}()",
                kind="debug",
            )
        elif event_type == "tool_result" and l5_tool_sse_enabled():
            tool = data.get("tool", "?")
            ok = data.get("success", True)
            ms = data.get("duration_ms")
            summary = data.get("action_summary") or data.get("error") or ""
            mark = "✓" if ok else "✗"
            dur = f" {ms}ms" if ms is not None else ""
            line = f"{mark} {tool}{dur}"
            if summary:
                line += f" — {summary}"
            self._append_line(step_index, line, kind="info" if ok else "error")

    def _set_active_step(self, index: int) -> None:
        self._active_index = index
        for i, item in enumerate(self._step_items):
            item.setExpanded(i == index)

    def _step_item(self, index: int) -> Optional[QTreeWidgetItem]:
        if index < 0 or index >= len(self._step_items):
            if self._step_items and self._active_index >= 0:
                return self._step_items[self._active_index]
            return None
        return self._step_items[index]

    def _append_line(self, step_index: int, text: str, *, kind: str = "info") -> None:
        parent = self._step_item(step_index)
        if parent is None:
            return
        dot = _LEVEL_DOT.get(kind, "·")
        child = QTreeWidgetItem([f"  {dot} {text}"])
        parent.addChild(child)
        parent.setExpanded(True)
        self._tree.scrollToItem(child)

    def _append_screenshot(self, step_index: int, b64: str) -> None:
        parent = self._step_item(step_index)
        if parent is None:
            return
        try:
            raw = b64.split(",", 1)[-1]
            img_data = base64.b64decode(raw)
            pix = QPixmap()
            if not pix.loadFromData(img_data):
                return
            thumb = pix.scaled(
                THUMB_W,
                THUMB_H,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        except Exception:
            return

        child = QTreeWidgetItem(["  📷 截屏"])
        parent.addChild(child)
        parent.setExpanded(True)

        label = QLabel()
        label.setPixmap(thumb)
        label.setCursor(Qt.PointingHandCursor)
        label.setToolTip("点击放大")
        full_pix = pix

        def _on_click(_ev, p=full_pix):
            dlg = _ScreenshotPreviewDialog(p, self.window())
            dlg.exec_()

        label.mousePressEvent = _on_click  # type: ignore[method-assign]
        self._tree.setItemWidget(child, 0, label)
        self._tree.scrollToItem(child)

    @property
    def total_steps(self) -> int:
        return self._total_steps

    @property
    def active_index(self) -> int:
        return self._active_index
