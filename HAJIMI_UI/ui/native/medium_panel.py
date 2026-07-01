from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QScrollArea,
    QTextEdit,
    QFrame,
    QProgressBar,
    QCheckBox,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QEvent, QSize, QTimer
from PyQt5.QtGui import QPainter

from config import API_BASE_URL, STOP_SERVICES_ON_EXIT, MODE_PILLS_MIN_WIDTH
from ui.chat_bubble import ChatBubble
from ui.step_list import StepListWidget
from ui.native.design_tokens import (
    DRAWER_WIDTH,
    CONTENT_PAD_H,
    CONTENT_PAD_V,
    CONTENT_PAD_BOTTOM,
    INPUT_DOCK_PAD,
)
from ui.native.nav_icons import nav_icon, svg_icon, action_icon
from ui.native.crystal_glass import paint_crystal_glass
from ui.native.widgets import (
    MenuButton,
    NavBackdrop,
    NotifRow,
    SetRow,
    ResizeHandleBar,
    animate_drawer,
)


PANEL_LABELS = {
    "guide": "操作指引",
    "steps": "步骤列表",
    "blueprint": "任务蓝图",
    "notifications": "提醒通知",
    "settings": "系统设置",
}

NAV_KEYS = list(PANEL_LABELS.keys())

PANEL_MODE_LEVEL = {
    "guide": 3,
    "steps": 2,
    "blueprint": 1,
    "notifications": 3,
    "settings": 3,
}


class _ChatEnterFilter(QObject):
    def __init__(self, submit_cb):
        super().__init__()
        self._submit = submit_cb

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self._submit()
                return True
        return False


class MediumPanel(QWidget):
    """中窗口 — 对齐 HTML #viewMedium (desktop-host)."""

    send_clicked = pyqtSignal(str)
    next_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    compact_requested = pyqtSignal()
    drag_requested = pyqtSignal()
    height_resize_drag = pyqtSignal(int)
    inspect_requested = pyqtSignal()
    inspect_exit_requested = pyqtSignal()
    start_services_requested = pyqtSignal()
    stop_services_requested = pyqtSignal()
    prepare_banner_clicked = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NativeShell")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self._drawer_visible = False

        self._backdrop = NavBackdrop(self)
        self._backdrop.clicked.connect(self._close_drawer)
        self._drawer = self._build_drawer()
        self._drawer.hide()

        main_col = QVBoxLayout(self)
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(0)

        self._resize_handle = ResizeHandleBar()
        self._resize_handle.drag_step.connect(self.height_resize_drag.emit)
        main_col.addWidget(self._resize_handle)

        self._topbar = self._build_topbar()
        main_col.addWidget(self._topbar)

        self._thinking_strip = QWidget()
        self._thinking_strip.setObjectName("ThinkingStrip")
        ts_layout = QVBoxLayout(self._thinking_strip)
        ts_layout.setContentsMargins(INPUT_DOCK_PAD, 0, INPUT_DOCK_PAD, 8)
        self._thinking_bar = QProgressBar()
        self._thinking_bar.setObjectName("ThinkingBar")
        self._thinking_bar.setTextVisible(False)
        self._thinking_bar.setRange(0, 0)
        self._thinking_bar.setFixedHeight(2)
        ts_layout.addWidget(self._thinking_bar)
        self._thinking_strip.hide()
        main_col.addWidget(self._thinking_strip)

        self._stage_hint = QLabel("")
        self._stage_hint.setObjectName("StageHint")
        self._stage_hint.hide()
        main_col.addWidget(self._stage_hint)

        self._content_scroll = QScrollArea()
        self._content_scroll.setObjectName("MediumContent")
        self._content_scroll.setWidgetResizable(True)
        self._content_scroll.setFrameShape(QFrame.NoFrame)
        self._content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_wrap = QWidget()
        content_wrap.setObjectName("MediumContentWrap")
        content_wrap.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        cw_layout = QVBoxLayout(content_wrap)
        cw_layout.setContentsMargins(
            CONTENT_PAD_H, CONTENT_PAD_V, CONTENT_PAD_H, CONTENT_PAD_BOTTOM
        )
        cw_layout.setSpacing(0)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_guide_page())
        self._pages.addWidget(self._build_steps_page())
        self._pages.addWidget(self._build_blueprint_page())
        self._pages.addWidget(self._build_notifications_page())
        self._pages.addWidget(self._build_settings_page())
        cw_layout.addWidget(self._pages)
        self._content_wrap = content_wrap
        self._content_scroll.setWidget(content_wrap)
        main_col.addWidget(self._content_scroll, 1)

        self._prepare_banner = self._build_prepare_banner()
        self._prepare_banner.hide()
        main_col.addWidget(self._prepare_banner)

        self._step_controls = self._build_step_controls()
        self._step_controls.hide()
        main_col.addWidget(self._step_controls)

        self._inspect_bar = self._build_inspect_bar()
        self._inspect_bar.hide()
        main_col.addWidget(self._inspect_bar)

        main_col.addWidget(self._build_input_dock())
        self._switch_panel("guide")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        paint_crystal_glass(painter, self.width(), self.height())
        painter.end()
        super().paintEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.height()
        self._backdrop.setGeometry(0, 0, self.width(), h)
        x = 0 if self._drawer_visible else -DRAWER_WIDTH
        self._drawer.setGeometry(x, 0, DRAWER_WIDTH, h)
        vp_w = self._content_scroll.viewport().width()
        if vp_w > 0:
            self._content_wrap.setMaximumWidth(vp_w)
        self._reflow_chat_bubbles()
        self._update_mode_pills_visibility()

    def _build_drawer(self) -> QWidget:
        drawer = QWidget(self)
        drawer.setObjectName("NavDrawer")
        drawer.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(drawer)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(4)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(svg_icon("logo", 16).pixmap(26, 26))
        logo.setObjectName("DrawerLogo")
        logo.setFixedSize(26, 26)
        logo.setAlignment(Qt.AlignCenter)
        head.addWidget(logo)
        title = QLabel("HAJIMI")
        title.setObjectName("DrawerHead")
        head.addWidget(title)
        head.addStretch()
        layout.addLayout(head)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setObjectName("DrawerSep")
        layout.addWidget(sep)

        self._nav_buttons = {}
        for key in NAV_KEYS:
            btn = QPushButton(PANEL_LABELS[key])
            btn.setObjectName("NavItem")
            btn.setProperty("active", "false")
            btn.setIcon(nav_icon(key, False))
            btn.setIconSize(QSize(18, 18))
            btn.clicked.connect(lambda checked, k=key: self._on_nav(k))
            layout.addWidget(btn)
            self._nav_buttons[key] = btn
            if key == "guide":
                compact_btn = QPushButton("小窗模式")
                compact_btn.setObjectName("NavItem")
                compact_btn.setProperty("active", "false")
                compact_btn.setToolTip("折叠为小窗口")
                compact_btn.setIcon(nav_icon("compact", False))
                compact_btn.setIconSize(QSize(18, 18))
                compact_btn.clicked.connect(self._on_compact_nav)
                layout.addWidget(compact_btn)

        layout.addStretch()

        quit_sep = QFrame()
        quit_sep.setFixedHeight(1)
        quit_sep.setObjectName("DrawerSep")
        layout.addWidget(quit_sep)

        quit_btn = QPushButton("退出")
        quit_btn.setObjectName("NavItemQuit")
        quit_btn.setIcon(nav_icon("logout", False))
        quit_btn.setIconSize(QSize(18, 18))
        quit_btn.clicked.connect(self._on_quit_nav)
        layout.addWidget(quit_btn)

        return drawer

    def _on_quit_nav(self):
        self._close_drawer()
        self.quit_requested.emit()

    def _on_compact_nav(self):
        self._close_drawer()
        self.compact_requested.emit()

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(CONTENT_PAD_H, 4, CONTENT_PAD_H, 10)
        layout.setSpacing(12)

        self._menu_btn = MenuButton()
        self._menu_btn.clicked.connect(self._toggle_drawer)
        layout.addWidget(self._menu_btn)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        title = QLabel("HAJIMI")
        title.setObjectName("TopTitle")
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._panel_sub = QLabel("操作指引")
        self._panel_sub.setObjectName("TopSub")
        self._panel_sub.setMinimumWidth(0)
        self._panel_sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text_col.addWidget(title)
        text_col.addWidget(self._panel_sub)
        layout.addLayout(text_col, 1)

        self._mode_pills = QWidget()
        self._mode_pills.setObjectName("ModePills")
        self._mode_pills.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        pl = QHBoxLayout(self._mode_pills)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)
        self._mode_pill_labels = []
        for label, active in (("L1", False), ("L2", False), ("L3", True)):
            pill = QLabel(label)
            pill.setObjectName("ModePill")
            pill.setProperty("active", "true" if active else "false")
            pl.addWidget(pill)
            self._mode_pill_labels.append(pill)
        layout.addWidget(self._mode_pills, 0)
        self._mode_pills.hide()

        self._status_badge = QLabel("● 准备就绪")
        self._status_badge.setObjectName("StatusBadge")
        self._status_badge.setProperty("status", "idle")
        self._status_badge.setMinimumWidth(0)
        self._status_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout.addWidget(self._status_badge, 0)
        return bar

    def _page_layout(self) -> QVBoxLayout:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        return page, layout

    def _build_guide_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self._welcome_bubble = ChatBubble(
            "你好！我是 HAJIMI 智能桌面指引助手。你可以问我类似于「怎么安装微信？」"
            "或「如何保存文档？」的操作问题。",
            "system",
        )
        layout.addWidget(self._welcome_bubble)

        self._chat_container = QWidget()
        self._chat_container.setObjectName("MediumChatContainer")
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(0, 0, 0, 0)
        self._chat_layout.setSpacing(12)
        self._chat_layout.setAlignment(Qt.AlignTop)
        layout.addWidget(self._chat_container, 0, Qt.AlignTop)

        self._guide_steps = StepListWidget()
        self._guide_steps.setObjectName("GuideSteps")
        layout.addWidget(self._guide_steps)
        layout.addStretch()
        return page

    def _build_steps_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        title = QLabel("Step Tracking")
        title.setObjectName("CardTitle")
        cl.addWidget(title)
        self._steps_list = StepListWidget()
        cl.addWidget(self._steps_list)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _build_blueprint_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(10)
        title = QLabel("Task Blueprint")
        title.setObjectName("CardTitle")
        cl.addWidget(title)
        meta = QHBoxLayout()
        meta.setSpacing(12)
        self._bp_count = QLabel("0 steps")
        self._bp_count.setObjectName("MetaRowLabel")
        self._bp_progress = QLabel("0 / 0")
        self._bp_progress.setObjectName("MetaRowLabel")
        meta.addWidget(self._bp_count)
        meta.addWidget(self._bp_progress)
        meta.addStretch()
        cl.addLayout(meta)
        self._bp_bar = QProgressBar()
        self._bp_bar.setObjectName("BlueprintProgress")
        self._bp_bar.setTextVisible(False)
        self._bp_bar.setFixedHeight(3)
        cl.addWidget(self._bp_bar)
        self._blueprint_list = StepListWidget()
        cl.addWidget(self._blueprint_list)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _build_notifications_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        title = QLabel("Notifications")
        title.setObjectName("CardTitle")
        cl.addWidget(title)
        for t, s, w in [
            ("C 盘空间不足", "剩余 8.2 GB", True),
            ("下载完成", "WeChatSetup.exe", False),
            ("新模板可用", "安装打印机驱动", False),
        ]:
            cl.addWidget(NotifRow(t, s, w))
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setSpacing(14)

        toggles = QFrame()
        toggles.setObjectName("Card")
        tl = QVBoxLayout(toggles)
        tl.setContentsMargins(16, 16, 16, 16)
        title = QLabel("Settings")
        title.setObjectName("CardTitle")
        tl.addWidget(title)
        for label, on in [
            ("语音播报", True),
            ("屏幕标注", True),
            ("快速路径", True),
            ("主动预警", False),
            ("隐私模式", True),
        ]:
            tl.addWidget(SetRow(label, on))
        il.addWidget(toggles)

        dev = QFrame()
        dev.setObjectName("Card")
        dl = QVBoxLayout(dev)
        dl.setContentsMargins(16, 16, 16, 16)
        dl.setSpacing(10)
        dev_title = QLabel("开发者")
        dev_title.setObjectName("SectionTitle")
        dl.addWidget(dev_title)

        inspect_row = QHBoxLayout()
        self._inspect_btn = QPushButton("立即检测当前屏幕")
        self._inspect_btn.setObjectName("StepBtnPrimary")
        self._inspect_btn.clicked.connect(self.inspect_requested.emit)
        inspect_row.addWidget(self._inspect_btn)
        exit_btn = QPushButton("退出检验")
        exit_btn.setObjectName("StepBtn")
        exit_btn.clicked.connect(self.inspect_exit_requested.emit)
        inspect_row.addWidget(exit_btn)
        dl.addLayout(inspect_row)

        self._inspect_status = QLabel("检验模式：未运行")
        self._inspect_status.setObjectName("HintText")
        self._inspect_status.setWordWrap(True)
        dl.addWidget(self._inspect_status)

        self._inspect_hint = QLabel(
            "CPU 本地检测约需 2–4 分钟，检测期间请勿重复点击。"
        )
        self._inspect_hint.setObjectName("HintTextSmall")
        self._inspect_hint.setWordWrap(True)
        dl.addWidget(self._inspect_hint)

        dl.addSpacing(8)
        svc_title = QLabel("后端服务")
        svc_title.setObjectName("SectionTitle")
        dl.addWidget(svc_title)

        api_lbl = QLabel(f"A 端地址：{API_BASE_URL}")
        api_lbl.setObjectName("HintText")
        api_lbl.setWordWrap(True)
        dl.addWidget(api_lbl)

        svc_row = QHBoxLayout()
        self._start_services_btn = QPushButton("启动 OmniParser + A 端")
        self._start_services_btn.setObjectName("StepBtnPrimary")
        self._start_services_btn.clicked.connect(self.start_services_requested.emit)
        svc_row.addWidget(self._start_services_btn)
        stop_btn = QPushButton("停止全部服务")
        stop_btn.setObjectName("StepBtn")
        stop_btn.clicked.connect(self.stop_services_requested.emit)
        svc_row.addWidget(stop_btn)
        dl.addLayout(svc_row)

        self._stop_on_exit_cb = QCheckBox("关闭窗口时停止 A 端与 OmniParser")
        self._stop_on_exit_cb.setChecked(STOP_SERVICES_ON_EXIT)
        dl.addWidget(self._stop_on_exit_cb)

        self._service_status = QLabel("")
        self._service_status.setObjectName("HintTextSmall")
        self._service_status.setWordWrap(True)
        dl.addWidget(self._service_status)

        il.addWidget(dev)
        il.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    def _build_prepare_banner(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("PrepareBanner")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        self._prepare_banner_btn = QPushButton("")
        self._prepare_banner_btn.setObjectName("PrepareBannerBtn")
        self._prepare_banner_btn.clicked.connect(self.prepare_banner_clicked.emit)
        layout.addWidget(self._prepare_banner_btn, 1)
        return bar

    def _build_step_controls(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("MediumStepControls")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(INPUT_DOCK_PAD, 8, INPUT_DOCK_PAD, 8)
        self._step_progress_label = QLabel("步骤 0 / 0")
        self._step_progress_label.setObjectName("StepProgressLabel")
        layout.addWidget(self._step_progress_label, 1)
        prev_btn = QPushButton("上一步")
        prev_btn.setObjectName("StepBtn")
        prev_btn.clicked.connect(self.prev_clicked.emit)
        next_btn = QPushButton("下一步")
        next_btn.setObjectName("StepBtnPrimary")
        next_btn.clicked.connect(self.next_clicked.emit)
        layout.addWidget(prev_btn)
        layout.addWidget(next_btn)
        return bar

    def _build_inspect_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("InspectBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        self._inspect_bar_label = QLabel("检验模式运行中")
        self._inspect_bar_label.setObjectName("InspectBarLabel")
        layout.addWidget(self._inspect_bar_label, 1)
        exit_btn = QPushButton("退出检验")
        exit_btn.setObjectName("StepBtn")
        exit_btn.clicked.connect(self.inspect_exit_requested.emit)
        layout.addWidget(exit_btn)
        return bar

    def _build_input_dock(self) -> QWidget:
        dock = QWidget()
        dock.setObjectName("InputDock")
        dl = QVBoxLayout(dock)
        dl.setContentsMargins(INPUT_DOCK_PAD, 0, INPUT_DOCK_PAD, INPUT_DOCK_PAD)

        float_card = QFrame()
        float_card.setObjectName("InputFloat")
        fl = QHBoxLayout(float_card)
        fl.setContentsMargins(12, 10, 10, 10)
        fl.setSpacing(8)
        fl.setAlignment(Qt.AlignBottom)

        self._input = QTextEdit()
        self._input.setObjectName("ChatInput")
        self._input.setPlaceholderText("输入消息…")
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._input.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._input.document().setDocumentMargin(2)
        line_h = self._input.fontMetrics().lineSpacing()
        self._input.setMinimumHeight(line_h + 6)
        self._input.setMaximumHeight(72)
        fl.addWidget(self._input, 1, Qt.AlignBottom)

        actions = QHBoxLayout()
        actions.setSpacing(2)
        mic_btn = QPushButton()
        mic_btn.setObjectName("IconBtnGhost")
        mic_btn.setIcon(action_icon("mic"))
        mic_btn.setFixedSize(32, 32)
        mic_btn.setToolTip("语音（即将推出）")
        mic_btn.setEnabled(False)
        self._send_btn = QPushButton()
        self._send_btn.setObjectName("SendBtnAccent")
        self._send_btn.setIcon(action_icon("send", "#5a9ec4"))
        self._send_btn.setFixedSize(32, 32)
        self._send_btn.clicked.connect(self._on_send)
        actions.addWidget(mic_btn)
        actions.addWidget(self._send_btn)
        fl.addLayout(actions, 0)

        self._chat_enter_filter = _ChatEnterFilter(self._on_send)
        self._input.installEventFilter(self._chat_enter_filter)
        dl.addWidget(float_card)
        return dock

    def _on_nav(self, panel: str):
        self._switch_panel(panel)
        self._close_drawer()

    def _toggle_drawer(self):
        if self._drawer_visible:
            self._close_drawer()
        else:
            self._open_drawer()

    def _open_drawer(self):
        self._drawer_visible = True
        self._menu_btn.set_open(True)
        animate_drawer(self._drawer, self._backdrop, True, self)

    def _close_drawer(self):
        if not self._drawer_visible:
            return
        self._drawer_visible = False
        self._menu_btn.set_open(False)
        animate_drawer(self._drawer, self._backdrop, False, self)

    def _switch_panel(self, panel: str):
        index = NAV_KEYS.index(panel) if panel in NAV_KEYS else 0
        self._pages.setCurrentIndex(index)
        self._panel_sub.setText(PANEL_LABELS.get(panel, panel))
        for key, btn in self._nav_buttons.items():
            active = key == panel
            btn.setProperty("active", "true" if active else "false")
            btn.setIcon(nav_icon(key, active))
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._update_mode_pill_highlight(panel)

    def _update_mode_pill_highlight(self, panel: str):
        level = PANEL_MODE_LEVEL.get(panel, 3)
        for i, pill in enumerate(self._mode_pill_labels, start=1):
            active = i == level
            pill.setProperty("active", "true" if active else "false")
            pill.style().unpolish(pill)
            pill.style().polish(pill)

    def _update_mode_pills_visibility(self):
        show = self.width() >= MODE_PILLS_MIN_WIDTH
        if show:
            if not self._mode_pills.isVisible():
                self._mode_pills.show()
        else:
            self._mode_pills.hide()

    def _on_send(self):
        if not self._input.isEnabled():
            return
        text = self._input.toPlainText().strip()
        if text:
            self._input.clear()
            self.send_clicked.emit(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            y = event.pos().y()
            if y > self._resize_handle.height() and y <= 80:
                self.drag_requested.emit()
        super().mousePressEvent(event)

    def _reflow_chat_bubbles(self):
        if hasattr(self, "_welcome_bubble"):
            self._welcome_bubble._reflow_bubble_width()
        for i in range(self._chat_layout.count()):
            item = self._chat_layout.itemAt(i)
            w = item.widget() if item else None
            if w and hasattr(w, "_reflow_bubble_width"):
                w._reflow_bubble_width()

    def append_message(self, text: str, msg_type: str = "system"):
        if "danger" in msg_type:
            bubble_type = "danger"
        elif msg_type == "user":
            bubble_type = "user"
        else:
            bubble_type = "system"
        self._chat_layout.addWidget(ChatBubble(text, bubble_type))
        QTimer.singleShot(0, self._reflow_chat_bubbles)
        sb = self._content_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_status_badge(self, status: str, label: str):
        self._status_badge.setText(f"● {label}")
        self._status_badge.setProperty("status", status)
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        if status == "processing":
            self._thinking_strip.show()
        else:
            self._thinking_strip.hide()
            self.set_stage_hint("")

    def set_stage_hint(self, text: str):
        if text:
            self._stage_hint.setText(text)
            self._stage_hint.show()
        else:
            self._stage_hint.hide()

    def set_input_enabled(self, enabled: bool):
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

    def show_prepare_banner(self, text: str):
        self._prepare_banner_btn.setText(f"⏳ 待重新定位：{text} — 点击继续")
        self._prepare_banner.show()

    def hide_prepare_banner(self):
        self._prepare_banner.hide()

    def update_steps(self, steps: list, active_index: int = 0):
        descriptions = [
            s.get("desc") or s.get("description") or s.get("action", "")
            for s in steps
        ]
        self._guide_steps.set_steps(descriptions, active_index)
        self._steps_list.set_steps(descriptions, active_index)
        total = len(descriptions)
        if total > 0 and active_index < total:
            self._step_controls.show()
            self._step_progress_label.setText(f"步骤 {active_index + 1} / {total}")
        else:
            self._step_controls.hide()

    def render_blueprint(self, steps: list, active_index: int = 0):
        descriptions = [
            s.get("desc") or s.get("description") or s.get("action", "")
            for s in steps
        ]
        self._blueprint_list.set_steps(descriptions, active_index)
        total = len(descriptions)
        self._bp_count.setText(f"{total} steps")
        if total and active_index >= total:
            self._bp_progress.setText(f"{total} / {total}")
            self._bp_bar.setValue(100)
        else:
            self._bp_progress.setText(f"{active_index + 1} / {total}")
            pct = int((active_index + 1) / total * 100) if total else 0
            self._bp_bar.setValue(pct)

    def set_inspect_busy(self, busy: bool):
        self._inspect_btn.setEnabled(not busy)
        self._inspect_btn.setText("检测中…" if busy else "立即检测当前屏幕")

    def set_inspect_status(self, text: str):
        if text:
            self._inspect_status.setText(text)
            if text.startswith("检验模式：") and "失败" not in text:
                self.set_inspect_bar_visible(True)
                self._inspect_bar_label.setText(text)
            elif text.startswith("检验失败"):
                self.set_inspect_bar_visible(False)
        else:
            self._inspect_status.setText("检验模式：未运行")
            self.set_inspect_bar_visible(False)

    def set_inspect_bar_visible(self, visible: bool):
        self._inspect_bar.show() if visible else self._inspect_bar.hide()

    def should_stop_services_on_exit(self) -> bool:
        return self._stop_on_exit_cb.isChecked()

    def set_service_status(self, text: str):
        if text:
            self._service_status.setText(text)

    def focus_input(self):
        self._input.setFocus()
