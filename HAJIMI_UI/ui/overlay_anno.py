from ui.native.design_tokens import (
    OVERLAY_HIGHLIGHT_RGB,
    OVERLAY_INSPECT_RGB,
    OVERLAY_ARROW_RGB,
)

import sys
import math
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPolygonF, QCursor

_HR, _HG, _HB = OVERLAY_HIGHLIGHT_RGB


def _physical_to_logical_rect(rect, scale: float):
    # 坐标已在 annotation_mapper 中转为逻辑像素，此处不再缩放
    return rect[0], rect[1], rect[2], rect[3]


def _physical_to_logical_point(pt, scale: float):
    return pt[0], pt[1]


class HighlightClickRegion(QWidget):
    """覆盖红框区域的可点击热区，不阻挡框外桌面操作。"""

    clicked = pyqtSignal()

    def __init__(self, x1: float, y1: float, x2: float, y2: float):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus,
        )
        width = max(1, int(x2 - x1))
        height = max(1, int(y2 - y1))
        self.setGeometry(int(x1), int(y1), width, height)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(_HR, _HG, _HB, 8))
        pen = QPen(QColor(_HR, _HG, _HB, 120), 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            print("[Overlay] 红框热区被点击")
            self.clicked.emit()
        event.accept()


class OverlayAnnoWindow(QWidget):
    """
    全屏透明屏幕覆盖层 (ANNO)
    负责在屏幕最上层动态绘制 AI 识别出的高亮框、编号标签和引导箭头。
    红框区域通过独立热区 Widget 接收点击。
    """

    sig_target_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.annotations = []
        self._click_regions: list = []
        self._init_window_attributes()
        self._log_screen_info()

    def _log_screen_info(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.geometry()
        dpr = screen.devicePixelRatio()
        print(
            f"[Overlay] 屏幕 geometry={geo.width()}x{geo.height()} "
            f"dpr={dpr} physical~{int(geo.width()*dpr)}x{int(geo.height()*dpr)}"
        )

    def _init_window_attributes(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.showFullScreen()

    def _scale_factor(self) -> float:
        return self.devicePixelRatioF()

    def _clear_click_regions(self):
        for region in self._click_regions:
            region.hide()
            region.deleteLater()
        self._click_regions = []

    def _sync_click_regions(self):
        self._clear_click_regions()
        scale = self._scale_factor()
        for item in self.annotations:
            if item.get("type") != "box":
                continue
            rect = item.get("rect", [0, 0, 0, 0])
            if len(rect) != 4:
                continue
            x1, y1, x2, y2 = _physical_to_logical_rect(rect, scale)
            region = HighlightClickRegion(x1, y1, x2, y2)
            region.clicked.connect(self._on_region_clicked)
            region.show()
            region.raise_()
            self._click_regions.append(region)

    def _on_region_clicked(self):
        self.sig_target_clicked.emit()

    def update_annotations(self, data_list):
        self.annotations = data_list or []
        self._sync_click_regions()
        self.update()
        for region in self._click_regions:
            region.raise_()

    def clear_annotations(self):
        self.annotations = []
        self._clear_click_regions()
        self.update()

    def paintEvent(self, event):
        if not self.annotations:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        scale_factor = self._scale_factor()

        for item in self.annotations:
            item_type = item.get("type")
            if item_type == "box":
                self._draw_highlighter_box(painter, item, scale_factor)
            elif item_type == "inspect_box":
                self._draw_inspect_box(painter, item, scale_factor)
            elif item_type == "arrow":
                self._draw_direction_arrow(painter, item, scale_factor)

        painter.end()

    def update_inspect_annotations(self, data_list):
        """检验模式：全量元素框，无点击热区。"""
        self._clear_click_regions()
        self.annotations = data_list or []
        self.update()

    def clear_inspect_annotations(self):
        self.annotations = []
        self.update()

    def _draw_inspect_box(self, painter, item, scale):
        rect_data = item.get("rect", [0, 0, 0, 0])
        label_text = str(item.get("label", ""))
        detail = str(item.get("detail", ""))
        x1, y1, x2, y2 = _physical_to_logical_rect(rect_data, scale)
        width, height = x2 - x1, y2 - y1

        ir, ig, ib = OVERLAY_INSPECT_RGB
        box_pen = QPen(QColor(ir, ig, ib, 200), 1)
        painter.setPen(box_pen)
        painter.setBrush(QBrush(QColor(ir, ig, ib, 15)))
        painter.drawRect(QRectF(x1, y1, width, height))

        tag = label_text
        if detail:
            tag = f"{label_text} {detail}"
        painter.setPen(QPen(QColor(0, 220, 255), 1))
        painter.setFont(QFont("Segoe UI" if sys.platform == "win32" else "Arial", 8))
        painter.drawText(QRectF(x1, max(0, y1 - 16), width + 120, 14), Qt.AlignLeft, tag)

    def _draw_highlighter_box(self, painter, item, scale):
        rect_data = item.get("rect", [0, 0, 0, 0])
        label_text = str(item.get("label", ""))
        x1, y1, x2, y2 = _physical_to_logical_rect(rect_data, scale)
        width, height = x2 - x1, y2 - y1

        box_pen = QPen(QColor(_HR, _HG, _HB, 220), 2)
        painter.setPen(box_pen)
        painter.setBrush(QBrush(QColor(_HR, _HG, _HB, 20)))
        painter.drawRect(QRectF(x1, y1, width, height))

        if label_text:
            radius = 11
            center_x, center_y = x1, y1
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(_HR, _HG, _HB, 240)))
            painter.drawEllipse(QPointF(center_x, center_y), radius, radius)
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.setFont(QFont("Segoe UI" if sys.platform == "win32" else "Arial", 9, QFont.Bold))
            text_rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)
            painter.drawText(text_rect, Qt.AlignCenter, label_text)

    def _draw_direction_arrow(self, painter, item, scale):
        from_pos = item.get("from", [0, 0])
        to_pos = item.get("to", [0, 0])
        if len(from_pos) != 2 or len(to_pos) != 2:
            return
        x1, y1 = _physical_to_logical_point(from_pos, scale)
        x2, y2 = _physical_to_logical_point(to_pos, scale)
        start_pt = QPointF(x1, y1)
        end_pt = QPointF(x2, y2)

        ar, ag, ab = OVERLAY_ARROW_RGB
        arrow_color = QColor(ar, ag, ab, 230)
        line_pen = QPen(arrow_color, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(line_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(start_pt, end_pt)

        dx, dy = x2 - x1, y2 - y1
        angle = math.atan2(dy, dx)
        arrow_length = 16
        arrow_angle = math.pi / 6
        p1_x = x2 - arrow_length * math.cos(angle - arrow_angle)
        p1_y = y2 - arrow_length * math.sin(angle - arrow_angle)
        p2_x = x2 - arrow_length * math.cos(angle + arrow_angle)
        p2_y = y2 - arrow_length * math.sin(angle + arrow_angle)

        arrow_head = QPolygonF([end_pt, QPointF(p1_x, p1_y), QPointF(p2_x, p2_y)])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(arrow_color))
        painter.drawPolygon(arrow_head)


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    overlay = OverlayAnnoWindow()
    overlay.update_annotations([
        {"type": "box", "rect": [150, 150, 450, 350], "label": "1"},
    ])
    sys.exit(app.exec_())
