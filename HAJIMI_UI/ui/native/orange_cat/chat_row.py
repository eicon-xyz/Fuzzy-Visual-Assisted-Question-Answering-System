"""Chat row with circular avatar above message bubble."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ui.chat_bubble import ChatBubble
from ui.native.orange_cat.circular_avatar import CircularAvatar, resolve_avatar_path


class OrangeCatChatRow(QWidget):
    """Avatar row on top, bubble below; AI left / user right."""

    def __init__(self, text: str, msg_type: str = "system", parent=None):
        super().__init__(parent)
        self.setObjectName("OrangeCatChatBubbleHost")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._msg_type = msg_type
        is_user = msg_type == "user"

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        avatar_row = QHBoxLayout()
        avatar_row.setContentsMargins(0, 0, 0, 0)
        avatar_row.setSpacing(0)

        self.avatar = CircularAvatar("user" if is_user else "ai")
        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(0, 0, 0, 0)
        bubble_row.setSpacing(0)
        self.bubble = ChatBubble(text, msg_type)

        if is_user:
            avatar_row.addStretch(1)
            avatar_row.addWidget(self.avatar, 0, Qt.AlignRight)
            bubble_row.addStretch(1)
            bubble_row.addWidget(self.bubble, 0, Qt.AlignRight)
        else:
            avatar_row.addWidget(self.avatar, 0, Qt.AlignLeft)
            avatar_row.addStretch(1)
            bubble_row.addWidget(self.bubble, 0, Qt.AlignLeft)
            bubble_row.addStretch(1)

        col.addLayout(avatar_row)
        col.addLayout(bubble_row)
        self.refresh_avatar()

    def refresh_avatar(self) -> None:
        path = resolve_avatar_path(self._msg_type)
        if path:
            self.avatar.set_image_path(path)
        else:
            self.avatar.clear_custom()

    def _reflow_bubble_width(self) -> None:
        if hasattr(self.bubble, "_reflow_bubble_width"):
            self.bubble._reflow_bubble_width()


# Demo alias
MaodiaoChatBubble = OrangeCatChatRow
