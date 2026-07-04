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
from PyQt5.QtGui import QIcon
from config import (
    STOP_SERVICES_ON_EXIT,
    MODE_PILLS_MIN_WIDTH,
    MEDIUM_WIDTH,
    MEDIUM_HEIGHT,
)
from core.user_settings import load_user_settings
from ui.native.window_state import clamp_size, _screen_max
from ui.chat_bubble import ChatBubble
from ui.step_list import StepListWidget
from ui.native.layout_tokens import (
    DRAWER_WIDTH,
    CONTENT_PAD_H,
    CONTENT_PAD_V,
    CONTENT_PAD_BOTTOM,
    INPUT_DOCK_PAD,
    MEDIUM_MIN_W,
)
from ui.native.layout.topbar_layout import build_topbar, compute_topbar_min_width
from ui.native.nav_icons import nav_icon, svg_icon, action_icon
from ui.native.shell_appearance import AppearanceSettings, is_luxury_theme
from ui.native.luxury.icons import apply_luxury_menu_icon, luxury_icon, luxury_nav_icon
from ui.native.luxury.title import ensure_luxury_fonts
from ui.native.status_badge_fx import BadgeBreathController
from ui.native.visual_tokens import accent_for_theme
from ui.native.widgets import (
    NavBackdrop,
    NotifRow,
    SetRow,
    animate_drawer,
    make_widget_transparent,
    make_scroll_area_transparent,
)
from ui.native.settings_widgets import (
    DeploymentModeGroup,
    SettingsFieldRow,
    SettingsEnterFilter,
    UiAppearanceGroup,
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
    inspect_requested = pyqtSignal()
    inspect_exit_requested = pyqtSignal()
    start_services_requested = pyqtSignal()
    stop_services_requested = pyqtSignal()
    settings_saved = pyqtSignal(dict)
    appearance_preview_requested = pyqtSignal(dict)
    panel_resize_requested = pyqtSignal(int, int)
    panel_restore_size = pyqtSignal()
    prepare_banner_clicked = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NativeShell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self._drawer_visible = False
        self._luxury_theme = False
        self._ui_theme = "current"
        self._current_panel = "guide"
        self._connection_error = False
        self._connection_tooltip = ""
        self._badge_status = "idle"
        self._badge_label = "准备就绪"
        self._topbar_narrow_min_w = MEDIUM_MIN_W
        self._topbar_full_min_w = MEDIUM_MIN_W
        self._settings_scroll = None
        self._settings_inner = None
        self._settings_size_timer = QTimer(self)
        self._settings_size_timer.setSingleShot(True)
        self._settings_size_timer.timeout.connect(self._emit_settings_size)

        self._backdrop = NavBackdrop(self)
        self._backdrop.clicked.connect(self._close_drawer)
        self._drawer = self._build_drawer()
        self._drawer.hide()

        main_col = QVBoxLayout(self)
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(0)

        self._topbar = self._build_topbar()
        make_widget_transparent(self._topbar)
        main_col.addWidget(self._topbar)
        self._badge_breath = BadgeBreathController(self._status_badge, self)

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
        make_scroll_area_transparent(self._content_scroll)

        content_wrap = QWidget()
        content_wrap.setObjectName("MediumContentWrap")
        content_wrap.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        make_widget_transparent(content_wrap)
        cw_layout = QVBoxLayout(content_wrap)
        cw_layout.setContentsMargins(
            CONTENT_PAD_H, CONTENT_PAD_V, CONTENT_PAD_H, CONTENT_PAD_BOTTOM
        )
        cw_layout.setSpacing(0)

        self._pages = QStackedWidget()
        self._pages.setObjectName("MediumPages")
        make_widget_transparent(self._pages)
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

        self._input_dock = self._build_input_dock()
        main_col.addWidget(self._input_dock)
        self._switch_panel("guide")
        self._refresh_status_badge()

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
        self._update_topbar_chrome()

    def _active_title_widget(self) -> QWidget:
        if self._luxury_theme and self._title_script.isVisible():
            return self._title_script
        return self._title_art

    def _recompute_topbar_widths(self) -> None:
        title = self._active_title_widget()
        self._topbar_narrow_min_w = compute_topbar_min_width(
            title,
            self._panel_sub,
            self._status_badge,
            include_panel_sub=False,
        )
        self._topbar_full_min_w = compute_topbar_min_width(
            title,
            self._panel_sub,
            self._status_badge,
            include_panel_sub=True,
            title_sep=self._title_sep,
        )

    def topbar_min_width(self, *, include_panel_sub: bool = False) -> int:
        self._recompute_topbar_widths()
        if include_panel_sub:
            return self._topbar_full_min_w
        return self._topbar_narrow_min_w

    def topbar_full_width(self) -> int:
        return self.topbar_min_width(include_panel_sub=True)

    def _update_panel_sub_visibility(self) -> None:
        self._recompute_topbar_widths()
        show_sub = self.width() >= self._topbar_full_min_w
        self._title_sep.setVisible(show_sub)
        self._panel_sub.setVisible(show_sub)

    def _update_topbar_chrome(self) -> None:
        self._update_panel_sub_visibility()
        self._update_mode_pills_visibility()

    def _refresh_status_badge(self) -> None:
        if self._badge_status in ("processing", "executing", "suspended"):
            status, label = self._badge_status, self._badge_label
            tooltip = ""
            breath = status == "processing" and not self._connection_error
        elif self._connection_error:
            status, label = "error", "A端不可达"
            tooltip = self._connection_tooltip
            breath = False
        else:
            status, label = self._badge_status, self._badge_label
            tooltip = ""
            breath = False
        self._status_badge.setText(f"● {label}")
        self._status_badge.setProperty("status", status)
        self._status_badge.setToolTip(tooltip)
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._status_badge.adjustSize()
        self._status_badge.setFixedWidth(self._status_badge.sizeHint().width())
        self._status_badge.show()
        if breath:
            if hasattr(self, "_thinking_strip"):
                self._thinking_strip.show()
            self._badge_breath.start()
        else:
            if hasattr(self, "_thinking_strip"):
                self._thinking_strip.hide()
            self._badge_breath.stop()
            if status in ("idle", "error"):
                self.set_stage_hint("")

    def _build_drawer(self) -> QWidget:
        drawer = QWidget(self)
        drawer.setObjectName("NavDrawer")
        drawer.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(drawer)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(4)

        head = QHBoxLayout()
        self._drawer_logo = QLabel()
        self._drawer_logo.setPixmap(svg_icon("logo", 16).pixmap(26, 26))
        self._drawer_logo.setObjectName("DrawerLogo")
        self._drawer_logo.setFixedSize(26, 26)
        self._drawer_logo.setAlignment(Qt.AlignCenter)
        head.addWidget(self._drawer_logo)
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
                self._compact_nav_btn = QPushButton("小窗模式")
                self._compact_nav_btn.setObjectName("NavItem")
                self._compact_nav_btn.setProperty("active", "false")
                self._compact_nav_btn.setToolTip("折叠为小窗口")
                self._compact_nav_btn.setIcon(nav_icon("compact", False))
                self._compact_nav_btn.setIconSize(QSize(18, 18))
                self._compact_nav_btn.clicked.connect(self._on_compact_nav)
                layout.addWidget(self._compact_nav_btn)

        layout.addStretch()

        quit_sep = QFrame()
        quit_sep.setFixedHeight(1)
        quit_sep.setObjectName("DrawerSep")
        layout.addWidget(quit_sep)

        self._quit_nav_btn = QPushButton("退出")
        self._quit_nav_btn.setObjectName("NavItemQuit")
        self._quit_nav_btn.setIcon(nav_icon("logout", False))
        self._quit_nav_btn.setIconSize(QSize(18, 18))
        self._quit_nav_btn.clicked.connect(self._on_quit_nav)
        layout.addWidget(self._quit_nav_btn)

        return drawer

    def _on_quit_nav(self):
        self._close_drawer()
        self.quit_requested.emit()

    def _on_compact_nav(self):
        self._close_drawer()
        self.compact_requested.emit()

    def _build_topbar(self) -> QWidget:
        result = build_topbar(self)
        self._menu_btn = result.menu_btn
        self._menu_btn.clicked.connect(self._toggle_drawer)
        self._title_art = result.title_art
        self._title_script = result.title_script
        self._title_sep = result.title_sep
        self._panel_sub = result.panel_sub
        self._mode_pills = result.mode_pills
        self._mode_pill_labels = result.mode_pill_labels
        self._status_badge = result.status_badge
        self._recompute_topbar_widths()
        return result.bar

    def _page_layout(self) -> QVBoxLayout:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        return page, layout

    def _build_guide_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("MediumPage")
        make_widget_transparent(page)
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
        make_widget_transparent(self._chat_container)
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
        page.setObjectName("MediumPage")
        make_widget_transparent(page)
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
        page.setObjectName("MediumPage")
        make_widget_transparent(page)
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
        page.setObjectName("MediumPage")
        make_widget_transparent(page)
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
        page.setObjectName("MediumPage")
        make_widget_transparent(page)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        make_scroll_area_transparent(scroll)
        inner = QWidget()
        inner.setObjectName("SettingsScrollInner")
        make_widget_transparent(inner)
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

        self._deployment_mode = DeploymentModeGroup()
        self._deployment_mode.mode_changed.connect(self._on_deployment_mode_changed)
        il.addWidget(self._deployment_mode)

        self._appearance_group = UiAppearanceGroup()
        self._appearance_group.save_requested.connect(self._save_settings)
        self._appearance_group.appearance_preview_requested.connect(
            self._forward_appearance_preview
        )
        self._appearance_group.preview_layout_changed.connect(
            self._schedule_settings_size
        )
        il.addWidget(self._appearance_group)

        api_card = QFrame()
        api_card.setObjectName("Card")
        al = QVBoxLayout(api_card)
        al.setContentsMargins(16, 16, 16, 16)
        al.setSpacing(4)
        api_title = QLabel("模型 API")
        api_title.setObjectName("SectionTitle")
        al.addWidget(api_title)

        self._field_a_url = SettingsFieldRow("A 端地址", "http://127.0.0.1:8010")
        self._field_demo_key = SettingsFieldRow("Demo Key", "hajimi-demo-2026")
        self._field_llm_base = SettingsFieldRow("问答 API Base", "https://api.deepseek.com")
        self._field_llm_key = SettingsFieldRow("问答 API Key", "", password=True)
        self._field_llm_model = SettingsFieldRow("问答模型名", "deepseek-chat")
        self._field_omni_url = SettingsFieldRow("OmniParser 地址", "http://127.0.0.1:8002")
        self._field_omni_gpu = SettingsFieldRow(
            "OmniParser GPU", "可选，SSH 隧道端口如 http://127.0.0.1:8002"
        )
        for row in (
            self._field_a_url,
            self._field_demo_key,
            self._field_llm_base,
            self._field_llm_key,
            self._field_llm_model,
            self._field_omni_url,
            self._field_omni_gpu,
        ):
            al.addWidget(row)

        save_row = QHBoxLayout()
        self._save_settings_btn = QPushButton("保存并应用")
        self._save_settings_btn.setObjectName("StepBtnPrimary")
        self._save_settings_btn.clicked.connect(self._save_settings)
        save_row.addWidget(self._save_settings_btn)
        save_row.addStretch()
        al.addLayout(save_row)

        self._settings_feedback = QLabel("")
        self._settings_feedback.setObjectName("HintTextSmall")
        self._settings_feedback.setWordWrap(True)
        al.addWidget(self._settings_feedback)

        self._settings_inputs = [
            self._field_a_url.input,
            self._field_demo_key.input,
            self._field_llm_base.input,
            self._field_llm_key.input,
            self._field_llm_model.input,
            self._field_omni_url.input,
            self._field_omni_gpu.input,
        ]
        self._settings_enter_filter = SettingsEnterFilter(self._save_settings)
        for inp in self._settings_inputs:
            inp.installEventFilter(self._settings_enter_filter)

        il.addWidget(api_card)

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

        self._api_lbl = QLabel("")
        self._api_lbl.setObjectName("HintText")
        self._api_lbl.setWordWrap(True)
        dl.addWidget(self._api_lbl)

        svc_row = QHBoxLayout()
        self._start_services_btn = QPushButton("启动 OmniParser + A 端")
        self._start_services_btn.setObjectName("StepBtnPrimary")
        self._start_services_btn.clicked.connect(self.start_services_requested.emit)
        svc_row.addWidget(self._start_services_btn)
        self._stop_services_btn = QPushButton("停止全部服务")
        self._stop_services_btn.setObjectName("StepBtn")
        self._stop_services_btn.clicked.connect(self.stop_services_requested.emit)
        svc_row.addWidget(self._stop_services_btn)
        dl.addLayout(svc_row)

        self._stop_on_exit_cb = QCheckBox("关闭窗口时停止 A 端与 OmniParser")
        self._stop_on_exit_cb.setChecked(STOP_SERVICES_ON_EXIT)
        dl.addWidget(self._stop_on_exit_cb)

        self._local_svc_widgets = (
            svc_title,
            self._start_services_btn,
            self._stop_services_btn,
            self._stop_on_exit_cb,
        )

        self._service_status = QLabel("")
        self._service_status.setObjectName("HintTextSmall")
        self._service_status.setWordWrap(True)
        dl.addWidget(self._service_status)

        il.addWidget(dev)
        il.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self._settings_scroll = scroll
        self._settings_inner = inner
        self.load_settings_form()
        return page

    def load_settings_form(self) -> None:
        data = load_user_settings()
        self._deployment_mode.set_mode(data.get("deployment_mode", "local"))
        self._appearance_group.set_appearance(data)
        self._appearance_group.sync_mode_sections()
        self._field_a_url.set_text(data.get("a_end_url", ""))
        self._field_demo_key.set_text(data.get("demo_key", ""))
        llm = data.get("llm") or {}
        self._field_llm_base.set_text(llm.get("base_url", ""))
        self._field_llm_key.set_text(llm.get("api_key", ""))
        self._field_llm_model.set_text(llm.get("model", ""))
        omni = data.get("omniparser") or {}
        self._field_omni_url.set_text(omni.get("url", ""))
        self._field_omni_gpu.set_text(omni.get("gpu_url", ""))
        self._apply_deployment_mode_ui(data.get("deployment_mode", "local"))

    def _forward_appearance_preview(self, data: dict) -> None:
        self.appearance_preview_requested.emit(data)

    def _collect_settings_data(self) -> dict:
        mode = self._deployment_mode.current_mode()
        a_url = self._field_a_url.text()
        if mode == "intranet" and not a_url:
            raise ValueError("内网 API 模式下 A 端地址为必填项")
        appearance = self._appearance_group.current_appearance()
        return {
            "deployment_mode": mode,
            **appearance,
            "a_end_url": a_url or "http://127.0.0.1:8010",
            "demo_key": self._field_demo_key.text() or "hajimi-demo-2026",
            "llm": {
                "base_url": self._field_llm_base.text(),
                "api_key": self._field_llm_key.text(),
                "model": self._field_llm_model.text() or "deepseek-chat",
            },
            "omniparser": {
                "url": self._field_omni_url.text() or "http://127.0.0.1:8002",
                "gpu_url": self._field_omni_gpu.text(),
            },
        }

    def _save_settings(self) -> None:
        try:
            data = self._collect_settings_data()
        except ValueError as exc:
            msg = str(exc)
            self._settings_feedback.setText(msg)
            self._appearance_group.set_feedback(msg)
            return
        self.settings_saved.emit(data)

    def _on_deployment_mode_changed(self, mode: str) -> None:
        self._apply_deployment_mode_ui(mode)

    def _apply_deployment_mode_ui(self, mode: str) -> None:
        intranet = mode == "intranet"
        for w in self._local_svc_widgets:
            w.setVisible(not intranet)
        llm_fields = (
            self._field_llm_base,
            self._field_llm_key,
            self._field_llm_model,
            self._field_omni_url,
            self._field_omni_gpu,
        )
        for row in llm_fields:
            row.set_enabled(not intranet)
        self._update_api_url_label()

    def _update_api_url_label(self) -> None:
        from config import API_BASE_URL

        self._api_lbl.setText(f"A 端地址：{API_BASE_URL}")

    def on_settings_applied(self, data: dict, success_msg: str = "") -> None:
        feedback = success_msg or "已保存并应用"
        self._settings_feedback.setText(feedback)
        self._appearance_group.set_feedback(feedback)
        self._apply_deployment_mode_ui(data.get("deployment_mode", "local"))
        self._update_api_url_label()

    def apply_appearance(
        self,
        appearance: AppearanceSettings | dict | None = None,
        *,
        ui_theme: str | None = None,
    ) -> None:
        if appearance is None:
            data = load_user_settings()
            appearance = AppearanceSettings.from_user_settings(data)
            if ui_theme is None:
                ui_theme = data.get("ui_theme", "current")
        elif isinstance(appearance, dict):
            if ui_theme is None:
                ui_theme = appearance.get("ui_theme", "current")
            appearance = AppearanceSettings.from_user_settings(appearance)
        theme_id = ui_theme or "current"
        self._ui_theme = theme_id
        luxury = is_luxury_theme(theme_id)
        self._luxury_theme = luxury
        if hasattr(self, "_title_art"):
            self._title_art.setVisible(not luxury)
            if not luxury:
                self._title_art.set_mode(appearance.title_art_mode)
                self._title_art.set_accent(accent_for_theme(theme_id))
                self._title_art.repaint()
        if hasattr(self, "_title_script"):
            self._title_script.setVisible(luxury)
            if luxury:
                ensure_luxury_fonts()
                self._title_script.set_font_id(appearance.luxury_script_font_id)
                self._title_script.set_gold_mode(appearance.luxury_gold_mode)
                self._title_script.repaint()
        if hasattr(self, "_menu_btn"):
            if luxury:
                apply_luxury_menu_icon(self._menu_btn)
            else:
                self._menu_btn.setIcon(QIcon())
                self._menu_btn.update()
        if hasattr(self, "_send_btn"):
            style = self._send_btn.style()
            if luxury:
                self._send_btn.setObjectName("SendBtnLuxHover")
                self._send_btn.setIcon(luxury_icon("send", 18))
            else:
                self._send_btn.setObjectName("SendBtnAccent")
                self._send_btn.setIcon(action_icon("send", accent_for_theme(theme_id)))
            style.unpolish(self._send_btn)
            style.polish(self._send_btn)
            self._send_btn.update()
        self._refresh_nav_icons()
        if hasattr(self, "_topbar"):
            self._topbar.repaint()
        self._recompute_topbar_widths()
        self._update_topbar_chrome()
        self._refresh_status_badge()

    def _nav_icon(self, key: str, active: bool) -> QIcon:
        if self._luxury_theme:
            return luxury_nav_icon(key, active)
        return nav_icon(key, active)

    def _refresh_nav_icons(self) -> None:
        if hasattr(self, "_drawer_logo"):
            if self._luxury_theme:
                self._drawer_logo.setPixmap(
                    luxury_icon("logo", 16).pixmap(26, 26)
                )
            else:
                self._drawer_logo.setPixmap(
                    svg_icon("logo", 16).pixmap(26, 26)
                )
        for key, btn in self._nav_buttons.items():
            active = btn.property("active") == "true"
            btn.setIcon(self._nav_icon(key, active))
        if hasattr(self, "_compact_nav_btn"):
            self._compact_nav_btn.setIcon(
                luxury_icon("compact", 16) if self._luxury_theme else nav_icon("compact", False)
            )
        if hasattr(self, "_quit_nav_btn"):
            self._quit_nav_btn.setIcon(
                luxury_icon("logout", 16) if self._luxury_theme else nav_icon("logout", False)
            )

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
        make_widget_transparent(dock)
        dl = QVBoxLayout(dock)
        dl.setContentsMargins(INPUT_DOCK_PAD, 0, INPUT_DOCK_PAD, INPUT_DOCK_PAD)

        float_card = QFrame()
        float_card.setObjectName("InputFloat")
        fl = QHBoxLayout(float_card)
        fl.setContentsMargins(12, 8, 10, 8)
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

    def force_dismiss_drawer(self) -> None:
        """Hide drawer overlay immediately (e.g. before mode switch)."""
        self._drawer_visible = False
        self._menu_btn.set_open(False)
        self._backdrop.hide()
        self._drawer.hide()
        effect = self._backdrop.graphicsEffect()
        if effect is not None:
            effect.setOpacity(0.0)

    def _switch_panel(self, panel: str):
        prev = self._current_panel
        self._current_panel = panel
        index = NAV_KEYS.index(panel) if panel in NAV_KEYS else 0
        self._pages.setCurrentIndex(index)
        self._panel_sub.setText(PANEL_LABELS.get(panel, panel))
        self._recompute_topbar_widths()
        self._update_topbar_chrome()
        for key, btn in self._nav_buttons.items():
            active = key == panel
            btn.setProperty("active", "true" if active else "false")
            btn.setIcon(self._nav_icon(key, active))
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._update_mode_pill_highlight(panel)

        if panel == "settings":
            if self._settings_scroll is not None:
                self._settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._schedule_settings_size()
        elif prev == "settings":
            self._cancel_settings_size_timer()
            if self._settings_scroll is not None:
                self._settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.panel_restore_size.emit()

    def current_panel(self) -> str:
        return self._current_panel

    def _settings_chrome_size(self) -> tuple[int, int]:
        main_margin_h = 0
        main_margin_v = 0
        panel_chrome_h = (
            self._topbar.sizeHint().height()
            + self._input_dock.sizeHint().height()
            + CONTENT_PAD_V
            + CONTENT_PAD_BOTTOM
        )
        panel_chrome_w = CONTENT_PAD_H * 2
        return main_margin_h + panel_chrome_w, main_margin_v + panel_chrome_h

    def _compute_settings_window_size(self) -> tuple[int, int]:
        if self._settings_inner is None:
            return MEDIUM_WIDTH, MEDIUM_HEIGHT

        self._settings_inner.adjustSize()
        hint = self._settings_inner.sizeHint()
        chrome_w, chrome_h = self._settings_chrome_size()

        need_w = hint.width() + chrome_w
        need_h = hint.height() + chrome_h

        max_w, max_h = _screen_max()
        target_w = max(MEDIUM_MIN_W, need_w)
        ratio_h = int(target_w * MEDIUM_HEIGHT / MEDIUM_WIDTH)
        target_h = max(need_h, ratio_h)
        return clamp_size(target_w, target_h)

    def _schedule_settings_size(self) -> None:
        if self._current_panel != "settings":
            return
        self._settings_size_timer.start(0)

    def _cancel_settings_size_timer(self) -> None:
        self._settings_size_timer.stop()

    def _emit_settings_size(self):
        if self._current_panel != "settings":
            return
        w, h = self._compute_settings_window_size()
        self.panel_resize_requested.emit(w, h)

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

    def _press_can_drag(self, pos) -> bool:
        target = self.childAt(pos)
        if target is None:
            return True
        blocked_names = {
            "NavDrawer",
            "NavBackdrop",
            "MenuBtn",
            "SendBtnLuxHover",
            "SendBtnAccent",
            "InputFloat",
            "ChatInput",
            "SettingsInput",
            "bubble-user",
            "bubble-system",
            "Card",
            "StepBtn",
            "StepBtnPrimary",
            "IconBtnGhost",
            "PrepareBannerBtn",
            "SettingsRadio",
            "CollapseToggle",
        }
        interactive_types = (
            QPushButton,
            QTextEdit,
            QCheckBox,
            QProgressBar,
        )
        w = target
        while w and w is not self:
            name = w.objectName() or ""
            if name in blocked_names:
                return False
            if isinstance(w, interactive_types):
                return False
            w = w.parentWidget()
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._press_can_drag(event.pos()):
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

    def set_connection_error(self, visible: bool, tooltip: str = "") -> None:
        self._connection_error = visible
        self._connection_tooltip = tooltip if visible else ""
        self._refresh_status_badge()

    def set_status_badge(self, status: str, label: str):
        self._badge_status = status
        self._badge_label = label
        self._refresh_status_badge()

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
        self._update_api_url_label()

    def focus_input(self):
        self._input.setFocus()
