from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize

from config import COMPACT_WIDTH
from ui.native.layout_tokens import COMPACT_HEIGHT


class CompactBar(QWidget):
    """小窗口 — 对齐 HTML #viewCompact (desktop-host: 固定 52px)."""

    submit_query = pyqtSignal(str)
    expand_requested = pyqtSignal()
    drag_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CompactShell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(COMPACT_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(12)

        mark = QLabel("✦")
        mark.setObjectName("CompactMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(32, 32)
        layout.addWidget(mark)

        self.input = QLineEdit()
        self.input.setObjectName("CompactInput")
        self.input.setPlaceholderText("Ask HAJIMI…")
        self.input.returnPressed.connect(self._on_enter)
        layout.addWidget(self.input, 1)

        hint = QLabel("↵")
        hint.setObjectName("CompactHint")
        layout.addWidget(hint)

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
            self.expand_requested.emit()

    def set_input_enabled(self, enabled: bool):
        self.input.setEnabled(enabled)

    def focus_input(self):
        self.input.setFocus()
