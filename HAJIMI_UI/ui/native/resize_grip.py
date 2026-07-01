"""8-direction resize for frameless medium window (helper, no overlay widget)."""
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import QPainter, QPen, QColor

from ui.native.design_tokens import ACCENT, MEDIUM_MIN_W, MEDIUM_MIN_H

GRIP = 14


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
        return {
            "l": Qt.SizeHorCursor,
            "r": Qt.SizeHorCursor,
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
            self._hover_edge = edge
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

    def paint_hover(self, painter: QPainter):
        if not self._hover_edge or not self._is_medium_mode():
            return
        r = self._panel_rect()
        painter.setPen(QPen(QColor(ACCENT), 2))
        m = GRIP // 2
        edge = self._hover_edge
        left = r.x() + m
        right = r.x() + r.width() - m
        top = r.y() + m
        bottom = r.y() + r.height() - m
        if edge in ("l", "tl", "bl"):
            painter.drawLine(left, top, left, bottom)
        if edge in ("r", "tr", "br"):
            painter.drawLine(right, top, right, bottom)
        if edge in ("t", "tl", "tr"):
            painter.drawLine(left, top, right, top)
        if edge in ("b", "bl", "br"):
            painter.drawLine(left, bottom, right, bottom)

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
