from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QLabel,
    QSizePolicy,
    QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer

from ui.native.design_tokens import BUBBLE_MAX_RATIO, CONTENT_PAD_H


class ChatBubble(QWidget):
    """HTML .chat-bubble — 内容自适应宽度，最大 85%；user 右对齐."""

    _INNER_H_PAD = 24  # layout margins 10 + 14

    def __init__(self, text, msg_type="system", parent=None, full_width=False):
        super().__init__(parent)
        self._full_width = full_width
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._bubble = QFrame()
        self._bubble.setAttribute(Qt.WA_StyledBackground, True)
        self._bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
        inner = QVBoxLayout(self._bubble)
        inner.setContentsMargins(10, 10, 14, 10)
        inner.setSpacing(0)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        inner.addWidget(self.label)

        if msg_type == "user":
            self._bubble.setObjectName("bubble-user")
            self.label.setObjectName("bubbleUserLabel")
            outer.addStretch(1)
            outer.addWidget(self._bubble, 0, Qt.AlignRight)
        elif msg_type == "danger":
            self._bubble.setObjectName("bubble-danger")
            self.label.setObjectName("bubbleDangerLabel")
            outer.addWidget(self._bubble, 0, Qt.AlignLeft)
            outer.addStretch(1)
        else:
            self._bubble.setObjectName("bubble-system")
            self.label.setObjectName("bubbleSystemLabel")
            outer.addWidget(self._bubble, 0, Qt.AlignLeft)
            outer.addStretch(1)

        QTimer.singleShot(0, self._reflow_bubble_width)

    def _viewport_content_width(self) -> int:
        widget = self.parentWidget()
        while widget is not None:
            if isinstance(widget, QScrollArea):
                vp_w = widget.viewport().width()
                if vp_w > 0:
                    return max(80, vp_w - CONTENT_PAD_H * 2)
            widget = widget.parentWidget()
        w = self.width()
        if w > 0:
            return max(80, w)
        return 280

    def _max_bubble_width(self) -> int:
        container = self._viewport_content_width()
        if self._full_width:
            return container
        return max(80, int(container * BUBBLE_MAX_RATIO))

    def _reflow_bubble_width(self):
        cap = self._max_bubble_width()
        inner_max = max(40, cap - self._INNER_H_PAD)
        fm = self.label.fontMetrics()
        text = self.label.text() or ""
        natural = fm.horizontalAdvance(text)

        if self._full_width or natural > inner_max:
            bubble_w = cap
        else:
            bubble_w = min(cap, natural + self._INNER_H_PAD)

        label_w = max(40, bubble_w - self._INNER_H_PAD)
        self._bubble.setMaximumWidth(bubble_w)
        self._bubble.setMinimumWidth(0)
        self.label.setMaximumWidth(label_w)
        self.label.setMinimumWidth(0)
        self.label.setFixedWidth(label_w)

        text_h = self.label.heightForWidth(label_w)
        if text_h > 0:
            self.label.setMinimumHeight(text_h)
        self._bubble.adjustSize()
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_bubble_width()

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow_bubble_width()
