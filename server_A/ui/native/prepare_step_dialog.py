from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.native.widgets import DialogCard, center_dialog_on_widget


class PrepareStepDialog(QDialog):
    """当前画面无法定位时，提示用户先手动操作，再重新截图定位。"""

    confirmed = pyqtSignal()
    dismissed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self._step_desc = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = DialogCard("prepare")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("请先完成这一步")
        title.setObjectName("DialogTitlePrepare")
        layout.addWidget(title)

        self._hint_label = QLabel("")
        self._hint_label.setObjectName("DialogBody")
        self._hint_label.setWordWrap(True)
        layout.addWidget(self._hint_label)

        sub = QLabel(
            "完成后点击下方按钮，HAJIMI 将分析新画面并在屏幕上标出点击位置。"
        )
        sub.setObjectName("DialogSub")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("稍后")
        self._cancel_btn.setObjectName("StepBtn")
        self._cancel_btn.clicked.connect(self._on_later)

        self._confirm_btn = QPushButton("我已完成，重新定位")
        self._confirm_btn.setObjectName("StepBtnPrimary")
        self._confirm_btn.clicked.connect(self._on_confirm)

        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._confirm_btn)
        layout.addLayout(btn_row)

        outer.addWidget(card)

    def show_hint(self, hint: str, step_desc: str = ""):
        self._step_desc = step_desc or hint
        text = hint or step_desc or "请按步骤说明完成操作后，再重新定位。"
        if step_desc and hint and step_desc not in hint:
            text = f"{step_desc}\n\n{hint}"
        self._hint_label.setText(text)
        self._set_busy(False)
        center_dialog_on_widget(self, self.parent())
        self.show()
        self.raise_()
        self.activateWindow()

    def set_busy(self, busy: bool):
        self._set_busy(busy)

    def _set_busy(self, busy: bool):
        self._confirm_btn.setEnabled(not busy)
        self._cancel_btn.setEnabled(not busy)
        if busy:
            self._confirm_btn.setText("定位中…")
        else:
            self._confirm_btn.setText("我已完成，重新定位")

    def _on_later(self):
        self.hide()
        self.dismissed.emit(self._step_desc)

    def _on_confirm(self):
        self._set_busy(True)
        self.hide()
        self.confirmed.emit()
