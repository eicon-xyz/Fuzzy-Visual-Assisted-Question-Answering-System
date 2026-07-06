from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.native.widgets import DialogCard, center_dialog_on_widget


class SuspensionDialog(QDialog):
    """步骤挂起确认对话框（skip / rollback / abort）"""

    resolved = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = DialogCard("suspension")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title = QLabel("操作挂起")
        title.setObjectName("DialogTitleSuspension")
        layout.addWidget(title)

        self._message_label = QLabel("")
        self._message_label.setObjectName("DialogBody")
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        skip_btn = QPushButton("跳过")
        skip_btn.setObjectName("StepBtn")
        skip_btn.clicked.connect(lambda: self._resolve("skip"))

        rollback_btn = QPushButton("回退重试")
        rollback_btn.setObjectName("StepBtnPrimary")
        rollback_btn.clicked.connect(lambda: self._resolve("rollback"))

        abort_btn = QPushButton("终止")
        abort_btn.setObjectName("StepBtn")
        abort_btn.clicked.connect(lambda: self._resolve("abort"))

        btn_row.addWidget(skip_btn)
        btn_row.addWidget(rollback_btn)
        btn_row.addWidget(abort_btn)
        layout.addLayout(btn_row)

        outer.addWidget(card)

    def show_message(self, message: str):
        self._message_label.setText(
            message or "检测到屏幕状态与预期不符，您要跳过此步还是回退重试？"
        )
        center_dialog_on_widget(self, self.parent())
        self.show()
        self.raise_()
        self.activateWindow()

    def _resolve(self, action: str):
        self.hide()
        self.resolved.emit(action)
