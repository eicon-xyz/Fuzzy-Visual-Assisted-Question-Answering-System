"""Reusable native UI widgets aligned with index.html."""
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect
from PyQt5.QtGui import QPainter, QPen, QColor

from ui.native.design_tokens import (
    DRAWER_WIDTH,
    ANIM_DRAWER_MS,
)
from ui.native.motion import animate_backdrop


def apply_shell_shadow(widget: QWidget):
    """HTML --glass-shadow on panel shell."""
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(40)
    fx.setOffset(0, 8)
    fx.setColor(QColor(0, 0, 0, 110))
    widget.setGraphicsEffect(fx)


class MenuButton(QPushButton):
    """Hamburger menu — three lines, toggles to X when open."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MenuBtn")
        self.setFixedSize(34, 34)
        self._open = False

    def set_open(self, open_: bool):
        self._open = open_
        self.setProperty("open", "true" if open_ else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def is_open(self) -> bool:
        return self._open

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#94a3b8"), 2, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        if self._open:
            painter.drawLine(int(cx - 6), int(cy - 6), int(cx + 6), int(cy + 6))
            painter.drawLine(int(cx + 6), int(cy - 6), int(cx - 6), int(cy + 6))
        else:
            for dy in (-5, 0, 5):
                painter.drawLine(int(cx - 7), int(cy + dy), int(cx + 7), int(cy + dy))
        painter.end()


class NavBackdrop(QWidget):
    """Semi-transparent overlay when drawer is open."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavBackdrop")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.hide()

    def mousePressEvent(self, event):
        self.clicked.emit()
        event.accept()


class DialogCard(QFrame):
    """Shared modal card — border variant via objectName suffix."""

    def __init__(self, variant: str = "default", parent=None):
        super().__init__(parent)
        name = "DialogCard"
        if variant == "prepare":
            name = "DialogCardPrepare"
        elif variant == "suspension":
            name = "DialogCardSuspension"
        self.setObjectName(name)


class CollapsibleSection(QWidget):
    """Expand/collapse section header + body."""

    toggled = pyqtSignal(bool)

    def __init__(self, title: str, parent=None, expanded: bool = True):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QHBoxLayout()
        self._toggle = QPushButton(("▼ " if expanded else "▶ ") + title)
        self._toggle.setObjectName("CollapseToggle")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.clicked.connect(self._on_toggle)
        row.addWidget(self._toggle, 1)
        layout.addLayout(row)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self._body)
        self._body.setVisible(expanded)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def set_expanded(self, expanded: bool):
        self._toggle.setChecked(expanded)
        self._body.setVisible(expanded)
        raw = self._toggle.text().lstrip("▼▶ ").strip()
        self._toggle.setText(("▼ " if expanded else "▶ ") + raw)

    def _on_toggle(self):
        open_ = self._toggle.isChecked()
        self._body.setVisible(open_)
        raw = self._toggle.text().lstrip("▼▶ ").strip()
        self._toggle.setText(("▼ " if open_ else "▶ ") + raw)
        self.toggled.emit(open_)


class NotifRow(QFrame):
    """HTML .notif / .notif.warn"""

    def __init__(self, title: str, subtitle: str, warn: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("NotifRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        if warn:
            self.setProperty("variant", "warn")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("NotifTitle")
        s = QLabel(subtitle)
        s.setObjectName("NotifSub")
        layout.addWidget(t)
        layout.addWidget(s)


class SetRow(QWidget):
    """HTML .set row with decorative toggle."""

    def __init__(self, label: str, on: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("SetRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 11, 0, 11)
        text = QLabel(label)
        text.setObjectName("SetRowLabel")
        sw = QFrame()
        sw.setObjectName("ToggleSwitch")
        sw.setFixedSize(38, 22)
        sw.setProperty("on", "true" if on else "false")
        sw.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(text, 1)
        layout.addWidget(sw, 0, Qt.AlignRight)


class ResizeHandleBar(QPushButton):
    """HTML .medium-resize-handle — 顶端居中横线，拖拽调整窗口高度."""

    drag_step = pyqtSignal(int)

    _BAR_W = 36
    _BAR_H = 3
    _BAR_W_HOVER = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MediumResizeHandle")
        self.setFixedHeight(14)
        self.setFlat(True)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip("上下拖动调整高度")
        self._dragging = False
        self._last_global_y = 0
        self._hovered = False

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bar_w = self._BAR_W_HOVER if self._hovered or self._dragging else self._BAR_W
        if self._hovered or self._dragging:
            color = QColor(90, 158, 196, 102 if self._dragging else 77)
        else:
            color = QColor(255, 255, 255, 38)
        x = (self.width() - bar_w) // 2
        y = (self.height() - self._BAR_H) // 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(x, y, bar_w, self._BAR_H, 2, 2)
        painter.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_global_y = event.globalY()
            self.grabMouse()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            dy = self._last_global_y - event.globalY()
            self._last_global_y = event.globalY()
            if dy:
                self.drag_step.emit(dy)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self.releaseMouse()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)


def center_dialog_on_widget(dialog, host: QWidget):
    """Center frameless dialog on the screen containing host."""
    if not host:
        return
    screen = host.screen() or host.window().screen()
    if not screen:
        return
    geo = screen.availableGeometry()
    dialog.adjustSize()
    x = geo.x() + (geo.width() - dialog.width()) // 2
    y = geo.y() + (geo.height() - dialog.height()) // 2
    dialog.move(x, y)


def animate_drawer(drawer: QWidget, backdrop: NavBackdrop, open_: bool, parent: QWidget):
    """Slide drawer from left; fade backdrop."""
    start_x = -DRAWER_WIDTH if not open_ else 0
    end_x = 0 if open_ else -DRAWER_WIDTH
    if open_:
        drawer.show()
        backdrop.show()
        backdrop.raise_()
        drawer.raise_()
        animate_backdrop(backdrop, True, parent)
    else:
        animate_backdrop(backdrop, False, parent)
    drawer.setFixedWidth(DRAWER_WIDTH)
    anim = QPropertyAnimation(drawer, b"geometry", parent)
    anim.setDuration(ANIM_DRAWER_MS)
    anim.setStartValue(QRect(start_x, 0, DRAWER_WIDTH, parent.height()))
    anim.setEndValue(QRect(end_x, 0, DRAWER_WIDTH, parent.height()))
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def on_finish():
        if not open_:
            drawer.hide()

    anim.finished.connect(on_finish)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
