# -*- coding: utf-8 -*-
"""L5 自动执行 — StepCard 步骤列表 + 每步截图/日志。"""
from __future__ import annotations

import os
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.native.l5_step_row import L5StepRow

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


def _step_instruction(step, index: int) -> str:
    if isinstance(step, dict):
        return (
            step.get("instruction")
            or step.get("description")
            or step.get("desc")
            or step.get("action")
            or f"步骤 {index + 1}"
        )
    return str(step)


class L5StepTimelineWidget(QWidget):
    """规划步骤列表（StepCard）+ 每步 SSE 截图/日志。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[L5StepRow] = []
        self._active_index = -1
        self._total_steps = 0
        self._planning = False
        self._pending_sse: list[tuple[str, dict]] = []
        self._plan_fingerprint: tuple[str, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)

        hint = QLabel("执行步骤（当前步自动展开详情）")
        hint.setObjectName("HintTextSmall")
        layout.addWidget(hint)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("L5StepScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.NoFrame)

        self._container = QWidget()
        self._container.setObjectName("L5StepList")
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch(1)

        self._placeholder = QLabel("◌ 规划步骤生成中…")
        self._placeholder.setObjectName("HintTextSmall")
        self._list_layout.insertWidget(0, self._placeholder)

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, 1)

    def _preview_pixmap(self, pixmap: QPixmap) -> None:
        dlg = _ScreenshotPreviewDialog(pixmap, self.window())
        dlg.exec_()

    def _clear_rows(self) -> None:
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

    def _remove_placeholder(self) -> None:
        if self._placeholder.parent():
            self._list_layout.removeWidget(self._placeholder)
            self._placeholder.hide()

    def _show_placeholder(self, text: str) -> None:
        self._clear_rows()
        self._placeholder.setText(text)
        if self._placeholder not in [
            self._list_layout.itemAt(i).widget()
            for i in range(self._list_layout.count())
            if self._list_layout.itemAt(i) and self._list_layout.itemAt(i).widget()
        ]:
            self._list_layout.insertWidget(0, self._placeholder)
        self._placeholder.show()

    def show_planning_placeholder(self) -> None:
        """规划等待期占位，避免空白步骤区。"""
        self._planning = True
        self._active_index = -1
        self._total_steps = 0
        self._plan_fingerprint = ()
        self._pending_sse.clear()
        self._show_placeholder("◌ 规划步骤生成中…")

    @property
    def is_planning(self) -> bool:
        return self._planning

    @property
    def is_tree_empty(self) -> bool:
        return len(self._rows) == 0 and not self._placeholder.isVisible()

    @staticmethod
    def plan_fingerprint(steps: list) -> tuple[str, ...]:
        return tuple(_step_instruction(s, i) for i, s in enumerate(steps))

    def reset_plan(self, steps: list) -> None:
        self._planning = False
        fingerprint = self.plan_fingerprint(steps)
        if fingerprint == self._plan_fingerprint and self._rows:
            return

        self._plan_fingerprint = fingerprint
        self._clear_rows()
        self._remove_placeholder()
        self._active_index = -1
        self._total_steps = len(steps)

        if not steps:
            self._show_placeholder("○ 暂无步骤（规划未返回）")
            self._plan_fingerprint = ()
            return

        stretch_idx = self._list_layout.count() - 1
        for i, step in enumerate(steps):
            text = _step_instruction(step, i)
            row = L5StepRow(
                i,
                text,
                preview_factory=self._preview_pixmap,
                parent=self._container,
            )
            self._list_layout.insertWidget(stretch_idx + i, row)
            self._rows.append(row)

        self.flush_pending()

    def flush_pending(self) -> None:
        if not self._rows:
            return
        pending = list(self._pending_sse)
        self._pending_sse.clear()
        for event_type, data in pending:
            self.handle_sse(event_type, data)

    def set_step_status(self, index: int, status: str) -> None:
        if index < 0 or index >= len(self._rows):
            return
        self._rows[index].set_status(status)

    def sync_active_index(self, active_index: int) -> None:
        """Update step status without clearing screenshots/logs."""
        if not self._rows:
            return
        for i in range(len(self._rows)):
            if active_index >= len(self._rows):
                self.set_step_status(i, "done")
            elif i < active_index:
                self.set_step_status(i, "done")
            elif i == active_index:
                self.set_step_status(i, "active")
                self._set_active_step(i)
            else:
                self.set_step_status(i, "pending")

    def step_instruction(self, index: int) -> str:
        if index < 0 or index >= len(self._rows):
            return ""
        return self._rows[index].instruction

    def show_initial_screenshot(self, step_index: int, b64: str) -> None:
        if b64:
            self._append_screenshot(step_index, b64)

    @staticmethod
    def _extract_screenshot_b64(data: dict) -> str:
        return (
            data.get("annotated_image")
            or data.get("image_base64")
            or data.get("screenshot_base64")
            or ""
        )

    def handle_sse(self, event_type: str, data: dict) -> None:
        if event_type == "screenshot_update":
            event_type = "screenshot_updated"
        step_index = int(data.get("step_index", 1)) - 1
        if not self._rows and event_type not in ("heartbeat",):
            self._pending_sse.append((event_type, data))
            return
        if event_type == "step_start":
            self._set_active_step(step_index)
            self.set_step_status(step_index, "active")
            self._append_line(step_index, "开始执行", kind="info")
        elif event_type == "log":
            level = str(data.get("level", "info"))
            msg = str(data.get("message", ""))
            if msg:
                self._append_line(step_index, msg, kind=level)
        elif event_type == "screenshot_updated":
            b64 = self._extract_screenshot_b64(data)
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
        for i, row in enumerate(self._rows):
            row.set_expanded(i == index)

    def _resolve_row(self, step_index: int) -> Optional[L5StepRow]:
        if 0 <= step_index < len(self._rows):
            return self._rows[step_index]
        if self._rows and self._active_index >= 0:
            return self._rows[self._active_index]
        return None

    def _append_line(self, step_index: int, text: str, *, kind: str = "info") -> None:
        row = self._resolve_row(step_index)
        if row is None:
            if self._rows:
                self._pending_sse.append(
                    ("log", {"step_index": step_index + 1, "level": kind, "message": text})
                )
            return
        row.append_log(text, kind=kind)
        if step_index == self._active_index:
            row.set_expanded(True)

    def _append_screenshot(self, step_index: int, b64: str) -> None:
        row = self._resolve_row(step_index)
        if row is None:
            self._pending_sse.append(
                (
                    "screenshot_updated",
                    {"step_index": step_index + 1, "annotated_image": b64},
                )
            )
            return
        row.add_screenshot(b64)

    def mark_completed(self, outcome: str = "done") -> None:
        """任务结束：展开全部步骤供回看，补全未标记的步骤状态。"""
        self._planning = False
        if outcome == "done":
            for row in self._rows:
                row.mark_all_done_if_pending()
        for row in self._rows:
            row.set_expanded(True)

    @property
    def total_steps(self) -> int:
        return self._total_steps

    @property
    def active_index(self) -> int:
        return self._active_index
