# main.py
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor
from ui.main_widget import MainWidget


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
    widget = MainWidget()
    widget.show()
    sys.exit(app.exec_())