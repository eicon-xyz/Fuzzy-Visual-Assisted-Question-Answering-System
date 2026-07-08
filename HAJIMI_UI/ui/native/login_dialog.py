"""B-end startup login dialog (DialogCard style)."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.auth_session import DEFAULT_DEMO_PASSWORD, DEFAULT_DEMO_USERNAME, login
from ui.native.widgets import DialogCard, center_dialog_on_widget


class LoginDialog(QDialog):
    """Modal login before MainWidget; does not change demo API auth."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setMinimumWidth(360)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = DialogCard("default")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("登录 HAJIMI")
        title.setObjectName("DialogTitlePrepare")
        layout.addWidget(title)

        hint = QLabel("演示账号已预填")
        hint.setObjectName("DialogSub")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._user_input = QLineEdit(DEFAULT_DEMO_USERNAME)
        self._user_input.setObjectName("SettingsInput")
        self._user_input.setPlaceholderText("用户名")
        layout.addWidget(self._user_input)

        self._pass_input = QLineEdit(DEFAULT_DEMO_PASSWORD)
        self._pass_input.setObjectName("SettingsInput")
        self._pass_input.setPlaceholderText("密码")
        self._pass_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self._pass_input)

        self._error_label = QLabel("")
        self._error_label.setObjectName("DialogSub")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #f87171;")
        self._error_label.hide()
        layout.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("StepBtn")
        cancel_btn.clicked.connect(self.reject)

        login_btn = QPushButton("登录")
        login_btn.setObjectName("StepBtnPrimary")
        login_btn.setDefault(True)
        login_btn.clicked.connect(self._on_login)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(login_btn)
        layout.addLayout(btn_row)

        outer.addWidget(card)

        self._pass_input.returnPressed.connect(self._on_login)
        self._user_input.returnPressed.connect(self._pass_input.setFocus)

    def show_centered(self) -> None:
        host = self.parent()
        if host is not None:
            center_dialog_on_widget(self, host)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.adjustSize()
                x = geo.x() + (geo.width() - self.width()) // 2
                y = geo.y() + (geo.height() - self.height()) // 2
                self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self._user_input.setFocus()

    def _on_login(self) -> None:
        username = self._user_input.text().strip()
        password = self._pass_input.text()
        if not username or not password:
            self._show_error("请输入用户名和密码")
            return
        try:
            login(username, password)
            self.accept()
        except Exception as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
