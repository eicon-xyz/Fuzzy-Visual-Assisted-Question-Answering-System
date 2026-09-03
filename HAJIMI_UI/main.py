# main.py
import os
import sys

from core.repo_paths import clear_shadow_client_modules, ensure_repo_root_on_path

ensure_repo_root_on_path()
clear_shadow_client_modules()

from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor

from core.auth_session import is_session_valid
from core.user_settings import apply_user_settings, load_user_settings

_settings = load_user_settings()
apply_user_settings(_settings)

from ui.main_widget import MainWidget
from ui.native.login_dialog import LoginDialog
from ui.native.shell_appearance import AppearanceSettings
from ui.native.theme_manager import get_theme_manager


def _apply_dark_palette(app: QApplication):
    palette = QPalette()
    text = QColor("#f1f5f9")
    window = QColor("#0f172a")
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.Base, QColor("#1e293b"))
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.ToolTipBase, window)
    palette.setColor(QPalette.PlaceholderText, QColor("#64748b"))
    app.setPalette(palette)


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QApplication(sys.argv)
    _apply_dark_palette(app)
    appearance = AppearanceSettings.from_user_settings(_settings)
    get_theme_manager(app).apply(_settings.get("ui_theme", "current"), appearance)

    if os.environ.get("HAJIMI_SKIP_LOGIN", "").strip() not in ("1", "true", "yes"):
        if not is_session_valid():
            login_dlg = LoginDialog()
            login_dlg.show_centered()
            if login_dlg.exec_() != QDialog.Accepted:
                sys.exit(0)

    widget = MainWidget(startup_hints=[])
    widget.show()
    sys.exit(app.exec_())