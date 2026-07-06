import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QBrush, QColor, QLinearGradient, QPainterPath, QPen

CORNER_RADIUS = 24  # 稍微加大圆角，水晶质感更圆润


class CrystalPanel(QWidget):
    """升级版：深色水晶玻璃面板（自带高级光影与防溢出裁剪）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        radius = CORNER_RADIUS

        # ================================================================
        # 核心拯救：创建圆角裁剪路径（防高光溢出的安全罩）
        # ================================================================
        clip_path = QPainterPath()
        clip_path.addRoundedRect(0, 0, w, h, radius, radius)

        painter.save()  # 保存未裁剪状态
        painter.setClipPath(clip_path)  # 激活裁剪，此后的绘制绝不超出圆角

        # 1. 基础深色通透层（带一点点深夜蓝调，提升水晶的折射厚重感）
        base_grad = QLinearGradient(0, 0, 0, h)
        base_grad.setColorAt(0.0, QColor(20, 26, 48, 180))  # 半透明深蓝
        base_grad.setColorAt(1.0, QColor(10, 14, 26, 220))  # 底部渐浓
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(base_grad))
        painter.drawRect(0, 0, w, h)

        # 2. 水晶表面尖锐反光（对角线强高光，模拟硬质表面折射）
        high_grad = QLinearGradient(0, 0, w, h * 0.6)  # 控制高光只停留在上半区
        high_grad.setColorAt(0.0, QColor(255, 255, 255, 45))  # 亮区： crisp white
        high_grad.setColorAt(0.15, QColor(255, 255, 255, 15))  # 快速衰减
        high_grad.setColorAt(0.4, QColor(255, 255, 255, 0))  # 迅速化为无形
        high_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(high_grad))
        painter.drawRect(0, 0, w, h)

        # 3. 底部次级折射光（模拟光线从水晶内部折射出来的幽光）
        bottom_grad = QLinearGradient(0, h, 0, 0)
        bottom_grad.setColorAt(0.0, QColor(100, 150, 255, 25))  # 淡淡的晶体蓝光
        bottom_grad.setColorAt(0.3, QColor(100, 150, 255, 0))
        painter.setBrush(QBrush(bottom_grad))
        painter.drawRect(0, 0, w, h)

        painter.restore()  # 恢复未裁剪状态，用来绘制高精度的边缘线

        # ================================================================
        # 水晶的灵魂：高精细渐变微光边框
        # ================================================================
        border_path = QPainterPath()
        # 向内微调 0.5 像素，防止抗锯齿导致边框和背景之间出现缝隙
        border_path.addRoundedRect(0.5, 0.5, w - 1, h - 1, radius, radius)

        border_grad = QLinearGradient(0, 0, w, h)
        border_grad.setColorAt(0.0, QColor(255, 255, 255, 110))  # 左上角：迎光面，极亮
        border_grad.setColorAt(0.2, QColor(255, 255, 255, 40))  # 过渡
        border_grad.setColorAt(0.5, QColor(255, 255, 255, 15))  # 侧面微弱反光
        border_grad.setColorAt(0.8, QColor(0, 0, 0, 50))  # 右下角：暗面阴影
        border_grad.setColorAt(1.0, QColor(0, 0, 0, 90))

        # 使用 1.2 像素的精致细线
        pen = QPen(QBrush(border_grad), 1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(border_path)

        painter.end()


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("高级深色水晶玻璃 — HAJIMI UI")
        self.setMinimumSize(800, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 40, 50, 40)
        layout.addWidget(CrystalPanel())

    def paintEvent(self, event):
        """绘制深色星空背景，衬托水晶面板的通透感"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(6, 10, 26))
        grad.setColorAt(0.5, QColor(12, 18, 38))
        grad.setColorAt(1.0, QColor(4, 6, 16))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRect(self.rect())
        painter.end()


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyleSheet("* { font-family: 'Segoe UI', sans-serif; }")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())