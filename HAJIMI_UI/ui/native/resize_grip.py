"""8-direction resize for frameless medium window (helper, no overlay widget)."""
from PyQt5.QtCore import Qt, QPoint, QRectF
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath

from ui.native.layout_tokens import MEDIUM_MIN_W, MEDIUM_MIN_H

_SHELL_GLASS_RGB = (15, 23, 42)
_SHELL_GLASS_ALPHA = 227

GRIP = 14
INSET = 2
IDLE_ALPHA = 20
HOVER_STROKE_ALPHA = 40
IDLE_SHORT = 24
HOVER_THICK = 3


class WindowResizeHandler:
    """Edge-drag resize — panel-relative coords; works via event filter on children."""

    def __init__(self, host: QWidget, panel_getter, is_medium_mode):
        self._host = host
        self._panel_getter = panel_getter
        self._is_medium_mode = is_medium_mode
        self._active_edge = None
        self._start_global = None
        self._start_geo = None
        self._hover_edge = None

    def set_enabled(self, enabled: bool):
        if not enabled:
            self._active_edge = None
            self._hover_edge = None
            self._host.unsetCursor()
            if self._host.mouseGrabber() is self._host:
                self._host.releaseMouse()

    def _panel_rect(self):
        panel = self._panel_getter()
        if panel is not None:
            return panel.geometry()
        return self._host.rect()

    def _host_pos(self, global_pos: QPoint) -> QPoint:
        return self._host.mapFromGlobal(global_pos)

    def _max_size(self):
        screen = self._host.screen() or QApplication.primaryScreen()
        if not screen:
            return 1920, 1080
        area = screen.availableGeometry()
        return int(area.width() * 0.9), int(area.height() * 0.9)

    @staticmethod
    def _lr_edge(edge):
        if not edge:
            return None
        if edge in ("l", "r"):
            return edge
        if edge in ("tl", "bl"):
            return "l"
        if edge in ("tr", "br"):
            return "r"
        return None

    def edge_at(self, host_pos: QPoint):
        r = self._panel_rect()
        x = host_pos.x() - r.x()
        y = host_pos.y() - r.y()
        w, h = r.width(), r.height()
        if x < 0 or y < 0 or x > w or y > h:
            return None
        left = x < GRIP
        right = x > w - GRIP
        top = y < GRIP
        bottom = y > h - GRIP
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if top:
            return "t"
        if bottom:
            return "b"
        if left:
            return "l"
        if right:
            return "r"
        return None

    def cursor_for(self, edge):
        lr = self._lr_edge(edge)
        if lr:
            return Qt.SizeHorCursor
        return {
            "t": Qt.SizeVerCursor,
            "b": Qt.SizeVerCursor,
            "tl": Qt.SizeFDiagCursor,
            "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor,
            "bl": Qt.SizeBDiagCursor,
        }.get(edge, Qt.ArrowCursor)

    def try_press_global(self, global_pos: QPoint, button) -> bool:
        if not self._is_medium_mode() or button != Qt.LeftButton:
            return False
        host_pos = self._host_pos(global_pos)
        edge = self.edge_at(host_pos)
        if not edge:
            return False
        self._active_edge = edge
        self._start_global = global_pos
        self._start_geo = self._host.geometry()
        self._host.grabMouse()
        return True

    def try_move_global(self, global_pos: QPoint) -> bool:
        if self._active_edge and self._start_global and self._start_geo:
            self._apply_resize(global_pos)
            return True
        if self._is_medium_mode():
            host_pos = self._host_pos(global_pos)
            edge = self.edge_at(host_pos)
            self._hover_edge = self._lr_edge(edge)
            if edge:
                self._host.setCursor(self.cursor_for(edge))
            else:
                self._host.unsetCursor()
            self._host.update()
        return False

    def try_release_global(self, global_pos: QPoint, button) -> bool:
        if not self._active_edge or button != Qt.LeftButton:
            return False
        self._active_edge = None
        self._start_global = None
        self._start_geo = None
        self._hover_edge = None
        if self._host.mouseGrabber() is self._host:
            self._host.releaseMouse()
        self._host.unsetCursor()
        if hasattr(self._host, "on_medium_resized"):
            self._host.on_medium_resized()
        return True

    def mouse_press(self, event) -> bool:
        return self.try_press_global(event.globalPos(), event.button())

    def mouse_move(self, event) -> bool:
        return self.try_move_global(event.globalPos())

    def mouse_release(self, event) -> bool:
        return self.try_release_global(event.globalPos(), event.button())

    def _idle_color(self) -> QColor:
        return QColor(255, 255, 255, IDLE_ALPHA)

    def _hover_fill(self) -> QColor:
        r, g, b = _SHELL_GLASS_RGB
        return QColor(r, g, b, _SHELL_GLASS_ALPHA)

    def _hover_stroke(self) -> QColor:
        return QColor(255, 255, 255, HOVER_STROKE_ALPHA)

    def _draw_v_capsule(self, painter: QPainter, x: float, y: float, w: float, h: float):
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), w / 2, w / 2)
        painter.setPen(Qt.NoPen)
        painter.fillPath(path, painter.brush())

    def _paint_idle_guides(self, painter: QPainter, r):
        painter.setPen(QPen(self._idle_color(), 1))
        cy = r.y() + r.height() / 2
        half = IDLE_SHORT / 2
        painter.drawLine(int(r.x() + INSET), int(cy - half), int(r.x() + INSET), int(cy + half))
        painter.drawLine(
            int(r.x() + r.width() - INSET), int(cy - half),
            int(r.x() + r.width() - INSET), int(cy + half),
        )

    def _paint_hover_guides(self, painter: QPainter, r, edge: str):
        left = r.x() + INSET
        right = r.x() + r.width() - INSET
        top = r.y() + INSET
        bottom = r.y() + r.height() - INSET
        thick = HOVER_THICK
        gap = 22
        painter.setBrush(self._hover_fill())
        painter.setPen(QPen(self._hover_stroke(), 1))
        if edge == "l":
            y0 = top + gap
            y1 = bottom - gap
            if y1 > y0:
                self._draw_v_capsule(painter, left, y0, thick, y1 - y0)
        elif edge == "r":
            y0 = top + gap
            y1 = bottom - gap
            if y1 > y0:
                self._draw_v_capsule(painter, right - thick, y0, thick, y1 - y0)

    def paint_resize_guides(self, painter: QPainter):
        if not self._is_medium_mode():
            return
        r = self._panel_rect()
        self._paint_idle_guides(painter, r)
        edge = self._hover_edge or self._lr_edge(self._active_edge)
        if edge in ("l", "r"):
            self._paint_hover_guides(painter, r, edge)

    def paint_hover(self, painter: QPainter):
        self.paint_resize_guides(painter)

    def _apply_resize(self, global_pos: QPoint):
        delta = global_pos - self._start_global
        g = self._start_geo
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        edge = self._active_edge
        max_w, max_h = self._max_size()

        if "l" in edge:
            nx = x + delta.x()
            nw = w - delta.x()
            if nw < MEDIUM_MIN_W:
                nx = x + w - MEDIUM_MIN_W
                nw = MEDIUM_MIN_W
            elif nw > max_w:
                nx = x + w - max_w
                nw = max_w
            x, w = nx, nw
        if "r" in edge:
            w = max(MEDIUM_MIN_W, min(max_w, w + delta.x()))
        if "t" in edge:
            ny = y + delta.y()
            nh = h - delta.y()
            if nh < MEDIUM_MIN_H:
                ny = y + h - MEDIUM_MIN_H
                nh = MEDIUM_MIN_H
            elif nh > max_h:
                ny = y + h - max_h
                nh = max_h
            y, h = ny, nh
        if "b" in edge:
            h = max(MEDIUM_MIN_H, min(max_h, h + delta.y()))

        self._host.setGeometry(x, y, w, h)
