from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap

from config import COMPACT_WIDTH
from ui.native.layout_tokens import COMPACT_HEIGHT


class CompactBar(QWidget):
    """小窗口 — 对齐 HTML #viewCompact (desktop-host: 固定 52px)."""

    submit_query = pyqtSignal(str)
    expand_requested = pyqtSignal()
    drag_requested = pyqtSignal()
    stop_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CompactShell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(COMPACT_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._l5_active = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(12)

        mark = QLabel("✦")
        mark.setObjectName("CompactMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(32, 32)
        self._mark = mark
        layout.addWidget(mark)

        self._l5_status = QLabel("")
        self._l5_status.setObjectName("CompactL5Status")
        self._l5_status.hide()
        layout.addWidget(self._l5_status, 1)

        self.input = QLineEdit()
        self.input.setObjectName("CompactInput")
        self.input.setPlaceholderText("Ask HAJIMI…")
        self.input.returnPressed.connect(self._on_enter)
        layout.addWidget(self.input, 1)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.setObjectName("StepBtn")
        self._stop_btn.hide()
        self._stop_btn.clicked.connect(self.stop_clicked.emit)
        layout.addWidget(self._stop_btn)

        hint = QLabel("↵")
        hint.setObjectName("CompactHint")
        self._enter_hint = hint
        layout.addWidget(hint)

    def set_l5_status(self, text: str, active: bool) -> None:
        self._l5_active = bool(active)
        if active and text:
            self._l5_status.setText(text)
            self._l5_status.show()
            self.input.hide()
            self._enter_hint.hide()
            self._stop_btn.show()
        else:
            self._l5_status.hide()
            self.input.show()
            self._enter_hint.show()
            self._stop_btn.hide()

    def preferred_size(self) -> QSize:
        return QSize(self.width() or COMPACT_WIDTH, COMPACT_HEIGHT)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.input.geometry().contains(event.pos()):
                self.expand_requested.emit()
        super().mousePressEvent(event)

    def _on_enter(self):
        if not self.input.isEnabled():
            return
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.submit_query.emit(text)
            if not self._l5_active:
                self.expand_requested.emit()

    def set_input_enabled(self, enabled: bool):
        self.input.setEnabled(enabled)

    def focus_input(self):
        if self._l5_active:
            return
        self.input.setFocus()

    def apply_orange_cat_theme(self, enabled: bool) -> None:
        if enabled:
            from ui.native.orange_cat.circular_avatar import render_ai_avatar_pixmap

            self._mark.setPixmap(render_ai_avatar_pixmap(30))
            self._mark.setText("")
        else:
            self._mark.setPixmap(QPixmap())
            self._mark.setText("✦")
        self._mark.update()
