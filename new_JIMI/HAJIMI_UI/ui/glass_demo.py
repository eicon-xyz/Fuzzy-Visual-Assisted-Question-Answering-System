"""
深色水晶玻璃质感 PyQt5 页面背景
================================
纯深底 + 深色水晶玻璃矩形面板，无文字，纯展示质感。

运行方式:  python -m ui.glass_demo
"""

import sys

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QBrush, QColor, QLinearGradient

from ui.native.crystal_glass import paint_crystal_glass, CORNER_RADIUS


class CrystalPanel(QWidget):
    """深色水晶玻璃面板 — 纯质感，无文字。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        paint_crystal_glass(painter, self.width(), self.height(), radius=CORNER_RADIUS)
        painter.end()


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("深色水晶玻璃 · Dark Crystal — HAJIMI UI")
        self.setMinimumSize(800, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 36, 48, 36)
        layout.addWidget(CrystalPanel())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(4, 8, 20))
        grad.setColorAt(0.5, QColor(8, 14, 30))
        grad.setColorAt(1.0, QColor(3, 6, 16))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRect(self.rect())
        painter.end()


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyleSheet("""
        * { font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
