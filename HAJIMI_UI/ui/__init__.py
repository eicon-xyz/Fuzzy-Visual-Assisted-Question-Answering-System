from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt

class ChatBubble(QWidget):
    """对话气泡，支持三种类型：user / system / danger"""
    def __init__(self, text, msg_type='system', parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        if msg_type == 'user':
            self.setObjectName('bubble-user')
            layout.addStretch()
            layout.addWidget(self.label)
        else:
            if msg_type == 'danger':
                self.setObjectName('bubble-danger')
            else:
                self.setObjectName('bubble-system')
            layout.addWidget(self.label)
            layout.addStretch()

        self.setStyleSheet("""
            QWidget#bubble-user {
                background-color: #5a9ec4;
                border-radius: 12px;
                border-top-right-radius: 2px;
                margin: 4px 0px;
            }
            QWidget#bubble-system {
                background-color: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 12px;
                border-top-left-radius: 2px;
                color: #f1f5f9;
            }
            QWidget#bubble-danger {
                background-color: rgba(231,76,60,0.15);
                border: 1px solid rgba(231,76,60,0.3);
                border-radius: 12px;
                border-top-left-radius: 2px;
                color: #f87171;
            }
            QLabel {
                font-size: 13px;
                line-height: 1.4;
                color: inherit;
            }
        """)