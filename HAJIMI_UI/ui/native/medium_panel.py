from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QScrollArea,
    QTextEdit,
    QPlainTextEdit,
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
from ui.native.l5_timeline import L5StepTimelineWidget
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
from ui.native.shell_appearance import (
    AppearanceSettings,
    is_luxury_theme,
    is_orange_cat_theme,
)
from ui.native.luxury.icons import apply_luxury_menu_icon, luxury_icon, luxury_nav_icon
from ui.native.luxury.title import ensure_luxury_fonts
from ui.native.orange_cat.chat_row import OrangeCatChatRow
from ui.native.orange_cat.icons import orange_cat_icon, orange_cat_nav_icon
from ui.native.orange_cat.tokens import PRIMARY, PRIMARY_DARK
from ui.native.status_badge_fx import BadgeBreathController
from ui.native.visual_tokens import accent_for_theme, TEXT_TERTIARY
from ui.native.widgets import (
    NavBackdrop,
    NotifRow,
    SetRow,
    animate_drawer,
    make_widget_transparent,
    make_scroll_area_transparent,
)
from ui.native.settings_widgets import (
    ModelSettingsGroup,
    SettingsEnterFilter,
    UiAppearanceGroup,
    VoiceSettingsGroup,
)


PANEL_LABELS = {
    "guide": "操作指引",
    "steps": "步骤列表",
    "notifications": "提醒通知",
    "settings": "系统设置",
}

NAV_KEYS = list(PANEL_LABELS.keys())

_WELCOME_TEXT = (
    "你好！我是 HAJIMI 智能桌面助手（L5 自动执行模式）。"
    "直接下达操作指令，例如「打开记事本并输入你好」，"
    "HAJIMI 会自动操作鼠标键盘完成任务；执行前请确保屏幕无敏感内容。"
)

PANEL_MODE_LEVEL = {
    "guide": 3,
    "steps": 2,
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
    stop_clicked = pyqtSignal()
    compact_requested = pyqtSignal()
    drag_requested = pyqtSignal()
    start_services_requested = pyqtSignal()
    stop_services_requested = pyqtSignal()
    model_settings_saved = pyqtSignal(dict)
    appearance_settings_saved = pyqtSignal(dict)
    voice_settings_saved = pyqtSignal(dict)
    appearance_preview_requested = pyqtSignal(dict)
    mic_clicked = pyqtSignal()
    panel_resize_requested = pyqtSignal(int, int)
    panel_restore_size = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NativeShell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self._drawer_visible = False
        self._luxury_theme = False
        self._orange_cat_theme = False
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
        self._pages.addWidget(self._build_notifications_page())
        self._pages.addWidget(self._build_settings_page())
        cw_layout.addWidget(self._pages)
        self._content_wrap = content_wrap
        self._content_scroll.setWidget(content_wrap)
        main_col.addWidget(self._content_scroll, 1)

        self._step_controls = self._build_step_controls()
        self._step_controls.hide()
        main_col.addWidget(self._step_controls)

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
            status, label = "error", "Sidecar 不可达"
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

        self._welcome_bubble = ChatBubble(_WELCOME_TEXT, "system")
        self._guide_layout = layout
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
        header = QHBoxLayout()
        self._steps_title = QLabel("Step Tracking")
        self._steps_title.setObjectName("CardTitle")
        self._steps_l5_badge = QLabel("")
        self._steps_l5_badge.setObjectName("HintTextSmall")
        self._steps_l5_badge.hide()
        header.addWidget(self._steps_title)
        header.addWidget(self._steps_l5_badge)
        header.addStretch()
        cl.addLayout(header)
        self._steps_list = StepListWidget()
        cl.addWidget(self._steps_list)
        self._l5_timeline = L5StepTimelineWidget()
        self._l5_timeline.hide()
        cl.addWidget(self._l5_timeline, 1)
        layout.addWidget(card)
        layout.addStretch()
        self._l5_execution_mode = False
        self._l5_completed = False
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
        toggles.setVisible(False)

        self._model_group = ModelSettingsGroup()
        self._model_group.model_save_requested.connect(self._save_model_settings)
        self._l5_exec_group = self._model_group.l5_exec
        self._field_demo_key = self._model_group.field_demo_key
        self._field_llm_base = self._model_group.field_llm_base
        self._field_llm_key = self._model_group.field_llm_key
        self._field_llm_model = self._model_group.field_llm_model
        il.addWidget(self._model_group)

        self._appearance_group = UiAppearanceGroup()
        self._appearance_group.save_requested.connect(self._save_appearance_settings)
        self._appearance_group.appearance_preview_requested.connect(
            self._forward_appearance_preview
        )
        self._appearance_group.preview_layout_changed.connect(
            self._schedule_settings_size
        )
        il.addWidget(self._appearance_group)

        self._voice_group = VoiceSettingsGroup()
        self._voice_group.voice_save_requested.connect(self._save_voice_settings)
        il.addWidget(self._voice_group)

        self._settings_enter_filter = SettingsEnterFilter(self._save_model_settings)
        for inp in self._model_group.settings_inputs():
            inp.installEventFilter(self._settings_enter_filter)

        dev = QFrame()
        dev.setObjectName("Card")
        dl = QVBoxLayout(dev)
        dl.setContentsMargins(16, 16, 16, 16)
        dl.setSpacing(10)
        dev_title = QLabel("开发者")
        dev_title.setObjectName("SectionTitle")
        dl.addWidget(dev_title)

        svc_title = QLabel("后端服务（L5 Sidecar :8011）")
        svc_title.setObjectName("SectionTitle")
        dl.addWidget(svc_title)

        self._api_lbl = QLabel("")
        self._api_lbl.setObjectName("HintText")
        self._api_lbl.setWordWrap(True)
        dl.addWidget(self._api_lbl)

        svc_row = QHBoxLayout()
        self._start_services_btn = QPushButton("重启 L5 Sidecar")
        self._start_services_btn.setObjectName("StepBtnPrimary")
        self._start_services_btn.clicked.connect(self.start_services_requested.emit)
        svc_row.addWidget(self._start_services_btn)
        self._stop_services_btn = QPushButton("停止服务")
        self._stop_services_btn.setObjectName("StepBtn")
        self._stop_services_btn.clicked.connect(self.stop_services_requested.emit)
        svc_row.addWidget(self._stop_services_btn)
        svc_row.addStretch()
        dl.addLayout(svc_row)

        self._stop_on_exit_cb = QCheckBox("关闭窗口时停止 L5 Sidecar")
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
        self._appearance_group.set_appearance(data)
        self._appearance_group.sync_scheme_sections()
        if hasattr(self, "_voice_group"):
            self._voice_group.set_voice(data)
        self._field_demo_key.set_text(data.get("demo_key", ""))
        llm = data.get("llm") or {}
        self._field_llm_base.set_text(llm.get("base_url", ""))
        self._field_llm_key.set_text(llm.get("api_key", ""))
        self._field_llm_model.set_text(llm.get("model", ""))
        if hasattr(self, "_l5_exec_group"):
            self._l5_exec_group.set_values(data)
        if hasattr(self, "_model_group"):
            self._model_group.set_proxy(data)
        self._update_api_url_label()

    def _forward_appearance_preview(self, data: dict) -> None:
        self.appearance_preview_requested.emit(data)

    def _collect_model_settings(self) -> dict:
        payload = {
            "demo_key": self._field_demo_key.text() or "hajimi-demo-2026",
            "llm": {
                "base_url": self._field_llm_base.text(),
                "api_key": self._field_llm_key.text(),
                "model": self._field_llm_model.text() or "deepseek-chat",
            },
        }
        if hasattr(self, "_l5_exec_group"):
            payload.update(self._l5_exec_group.get_values())
        if hasattr(self, "_model_group"):
            payload.update(self._model_group.proxy_values())
        return payload

    def _collect_appearance_settings(self) -> dict:
        return self._appearance_group.current_appearance()

    def _save_model_settings(self) -> None:
        try:
            data = self._collect_model_settings()
        except ValueError as exc:
            self._model_group.set_feedback(str(exc))
            return
        self.model_settings_saved.emit(data)

    def _save_appearance_settings(self) -> None:
        self.appearance_settings_saved.emit(self._collect_appearance_settings())

    def _save_voice_settings(self) -> None:
        self.voice_settings_saved.emit({"voice": self._voice_group.current_voice()})

    def on_voice_settings_applied(self, data: dict, success_msg: str = "") -> None:
        feedback = success_msg or "已保存并应用"
        if hasattr(self, "_voice_group"):
            self._voice_group.set_feedback(feedback)
            self._voice_group.set_voice(data)

    def refresh_orange_cat_avatars(self) -> None:
        candidates: list = []
        if hasattr(self, "_welcome_bubble") and hasattr(
            self._welcome_bubble, "refresh_avatar"
        ):
            candidates.append(self._welcome_bubble)
        if hasattr(self, "_chat_layout"):
            for i in range(self._chat_layout.count()):
                item = self._chat_layout.itemAt(i)
                w = item.widget() if item else None
                if w is not None and hasattr(w, "refresh_avatar"):
                    candidates.append(w)
        for widget in candidates:
            widget.refresh_avatar()

    def _update_api_url_label(self) -> None:
        from config import L5_API_URL

        self._api_lbl.setText(f"L5 Sidecar (server_A)：{L5_API_URL}")

    def on_model_settings_applied(self, data: dict, success_msg: str = "") -> None:
        feedback = success_msg or "已保存并应用"
        self._model_group.set_feedback(feedback)
        self._update_api_url_label()

    def on_appearance_settings_applied(self, data: dict, success_msg: str = "") -> None:
        feedback = success_msg or "已保存并应用"
        self._appearance_group.set_feedback(feedback)

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
        orange = is_orange_cat_theme(theme_id)
        self._luxury_theme = luxury
        self._orange_cat_theme = orange
        if hasattr(self, "_title_art"):
            if orange:
                self._title_art.setVisible(True)
                self._title_art.set_mode("gradient")
                self._title_art.set_accent(PRIMARY)
                self._title_art.set_gradient_stops(PRIMARY_DARK, "#FFD4A3")
                self._title_art.repaint()
            else:
                self._title_art.setVisible(not luxury)
                if not luxury:
                    self._title_art.reset_gradient_stops()
                    self._title_art.set_mode(appearance.title_art_mode)
                    self._title_art.set_accent(accent_for_theme(theme_id))
                    self._title_art.repaint()
        if hasattr(self, "_title_script"):
            self._title_script.setVisible(luxury and not orange)
            if luxury:
                ensure_luxury_fonts()
                self._title_script.set_font_id(appearance.luxury_script_font_id)
                self._title_script.set_gold_mode(appearance.luxury_gold_mode)
                self._title_script.repaint()
        if hasattr(self, "_menu_btn"):
            if orange:
                self._menu_btn.setText("")
                self._menu_btn.setIcon(orange_cat_icon("menu", 24))
                self._menu_btn.update()
            elif luxury:
                apply_luxury_menu_icon(self._menu_btn)
            else:
                self._menu_btn.setIcon(QIcon())
                self._menu_btn.update()
        if hasattr(self, "_mic_btn"):
            if orange:
                self._mic_btn.setIcon(orange_cat_icon("mic", 24))
            else:
                self._mic_btn.setIcon(action_icon("mic"))
            self._mic_btn.update()
        if hasattr(self, "_send_btn"):
            style = self._send_btn.style()
            if orange:
                self._send_btn.setText("")
                self._send_btn.setObjectName("SendBtnOrange")
                self._send_btn.setIcon(orange_cat_icon("send", 24))
            elif luxury:
                self._send_btn.setObjectName("SendBtnLuxHover")
                self._send_btn.setIcon(luxury_icon("send", 18))
            else:
                self._send_btn.setObjectName("SendBtnAccent")
                self._send_btn.setIcon(action_icon("send", accent_for_theme(theme_id)))
            style.unpolish(self._send_btn)
            style.polish(self._send_btn)
            self._send_btn.update()
        if hasattr(self, "_input_float"):
            self._input_float.setAttribute(Qt.WA_StyledBackground, orange)
            float_style = self._input_float.style()
            float_style.unpolish(self._input_float)
            float_style.polish(self._input_float)
            self._input_float.update()
        if hasattr(self, "_input_dock"):
            if orange:
                self._input_dock.setAttribute(Qt.WA_TranslucentBackground, False)
                self._input_dock.setAttribute(Qt.WA_StyledBackground, True)
            else:
                make_widget_transparent(self._input_dock)
            dock_style = self._input_dock.style()
            dock_style.unpolish(self._input_dock)
            dock_style.polish(self._input_dock)
            self._input_dock.update()
        self._sync_welcome_bubble()
        if orange:
            self._repolish_chat_bubbles()
        self._refresh_nav_icons()
        if hasattr(self, "_topbar"):
            self._topbar.repaint()
        self._recompute_topbar_widths()
        self._update_topbar_chrome()
        self._refresh_status_badge()
        self.repaint()

    def _sync_welcome_bubble(self) -> None:
        if not hasattr(self, "_guide_layout") or not hasattr(self, "_welcome_bubble"):
            return
        want_orange = self._orange_cat_theme
        is_orange_row = isinstance(self._welcome_bubble, OrangeCatChatRow)
        if want_orange == is_orange_row:
            if want_orange and hasattr(self._welcome_bubble, "refresh_avatar"):
                self._welcome_bubble.refresh_avatar()
            return
        layout = self._guide_layout
        idx = layout.indexOf(self._welcome_bubble)
        layout.removeWidget(self._welcome_bubble)
        self._welcome_bubble.deleteLater()
        if want_orange:
            self._welcome_bubble = OrangeCatChatRow(_WELCOME_TEXT, "system")
        else:
            self._welcome_bubble = ChatBubble(_WELCOME_TEXT, "system")
        if idx >= 0:
            layout.insertWidget(idx, self._welcome_bubble)
        else:
            layout.addWidget(self._welcome_bubble)

    def _repolish_chat_bubbles(self) -> None:
        style = self.style()
        candidates: list[QWidget] = []
        if hasattr(self, "_welcome_bubble") and self._welcome_bubble is not None:
            candidates.append(self._welcome_bubble)
        if hasattr(self, "_chat_layout"):
            for i in range(self._chat_layout.count()):
                item = self._chat_layout.itemAt(i)
                w = item.widget() if item else None
                if w is not None:
                    candidates.append(w)
        for widget in candidates:
            style.unpolish(widget)
            style.polish(widget)
            widget.update()
            bubble_host = getattr(widget, "bubble", widget)
            inner = getattr(bubble_host, "_bubble", None)
            if inner is not None:
                style.unpolish(inner)
                style.polish(inner)
                inner.update()

    def _nav_icon(self, key: str, active: bool) -> QIcon:
        if self._orange_cat_theme:
            return orange_cat_nav_icon(key, active)
        if self._luxury_theme:
            return luxury_nav_icon(key, active)
        return nav_icon(key, active)

    def _refresh_nav_icons(self) -> None:
        if hasattr(self, "_drawer_logo"):
            if self._orange_cat_theme:
                from ui.native.orange_cat.icons import orange_cat_pixmap

                self._drawer_logo.setPixmap(orange_cat_pixmap("mark", 16))
            elif self._luxury_theme:
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

    def _build_step_controls(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("MediumStepControls")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(INPUT_DOCK_PAD, 8, INPUT_DOCK_PAD, 8)
        self._step_progress_label = QLabel("步骤 0 / 0")
        self._step_progress_label.setObjectName("StepProgressLabel")
        layout.addWidget(self._step_progress_label, 1)
        next_btn = QPushButton("下一步")
        next_btn.setObjectName("StepBtnPrimary")
        next_btn.clicked.connect(self.next_clicked.emit)
        stop_btn = QPushButton("停止")
        stop_btn.setObjectName("StepBtn")
        stop_btn.clicked.connect(self.stop_clicked.emit)
        pause_btn = QPushButton("暂停")
        pause_btn.setObjectName("StepBtn")
        pause_btn.setEnabled(False)
        pause_btn.setToolTip("Sidecar 升级 pause API 后可用；当前请用停止 (J)")
        self._step_next_btn = next_btn
        self._step_stop_btn = stop_btn
        self._step_pause_btn = pause_btn
        layout.addWidget(pause_btn)
        layout.addWidget(next_btn)
        layout.addWidget(stop_btn)
        return bar

    def _build_input_dock(self) -> QWidget:
        dock = QWidget()
        dock.setObjectName("InputDock")
        make_widget_transparent(dock)
        dl = QVBoxLayout(dock)
        dl.setContentsMargins(INPUT_DOCK_PAD, 0, INPUT_DOCK_PAD, INPUT_DOCK_PAD)

        float_card = QFrame()
        float_card.setObjectName("InputFloat")
        self._input_float = float_card
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
        self._speaker_btn = QPushButton()
        self._speaker_btn.setObjectName("IconBtnGhost")
        self._speaker_btn.setIcon(action_icon("speaker"))
        self._speaker_btn.setFixedSize(32, 32)
        self._speaker_btn.setToolTip("语音播报状态")
        self._speaker_btn.setEnabled(False)
        mic_btn = QPushButton()
        mic_btn.setObjectName("IconBtnGhost")
        mic_btn.setIcon(action_icon("mic"))
        mic_btn.setFixedSize(32, 32)
        mic_btn.setToolTip("点击说话（再次点击结束；静音 5 秒自动结束）")
        mic_btn.setEnabled(False)
        mic_btn.clicked.connect(self.mic_clicked.emit)
        self._mic_btn = mic_btn
        self._mic_recording = False
        self._send_btn = QPushButton()
        self._send_btn.setObjectName("SendBtnAccent")
        self._send_btn.setIcon(action_icon("send", "#5a9ec4"))
        self._send_btn.setFixedSize(32, 32)
        self._send_btn.clicked.connect(self._on_send)
        actions.addWidget(self._speaker_btn)
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

        if panel == "steps" and self._l5_execution_mode:
            self._apply_l5_steps_layout()
            if (
                self._l5_timeline.total_steps == 0
                and not self._l5_timeline.is_planning
                and self._l5_timeline.is_tree_empty
            ):
                self._l5_timeline.show_planning_placeholder()

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
        self._chat_layout.addWidget(
            OrangeCatChatRow(text, bubble_type)
            if self._orange_cat_theme
            else ChatBubble(text, bubble_type)
        )
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

    def set_mic_enabled(self, enabled: bool) -> None:
        if hasattr(self, "_mic_btn"):
            if getattr(self, "_mic_recording", False):
                self._mic_btn.setEnabled(True)
            else:
                self._mic_btn.setEnabled(enabled)
            self._mic_btn.setVisible(True)

    def set_mic_recording(self, recording: bool) -> None:
        """录音中：高亮麦克风；录音时仍允许再次点击结束。"""
        self._mic_recording = recording
        if not hasattr(self, "_mic_btn"):
            return
        accent = accent_for_theme(getattr(self, "_ui_theme", "current"))
        self._mic_btn.setIcon(
            action_icon("mic", accent if recording else TEXT_TERTIARY)
        )
        self._mic_btn.setToolTip(
            "录音中…再次点击结束" if recording else "点击说话（再次点击结束；静音 5 秒自动结束）"
        )
        if recording:
            self._mic_btn.setEnabled(True)

    def set_c_integration_status(self, text: str) -> None:
        if hasattr(self, "_voice_group"):
            self._voice_group.set_c_health_status(text)

    def focus_input(self) -> None:
        self._input.setFocus(Qt.OtherFocusReason)

    def set_speaker_playing(self, playing: bool) -> None:
        if not hasattr(self, "_speaker_btn"):
            return
        self._speaker_btn.setEnabled(True)
        self._speaker_btn.setVisible(True)
        accent = accent_for_theme(getattr(self, "_ui_theme", "current"))
        icon_key = "speaker"
        self._speaker_btn.setIcon(
            action_icon(icon_key, accent if playing else TEXT_TERTIARY)
            if playing
            else action_icon(icon_key)
        )
        self._speaker_btn.setToolTip("正在播报…" if playing else "语音播报")

    def set_input_from_asr(self, text: str, *, low_confidence: bool = False) -> None:
        self._input.setPlainText(text)
        if low_confidence:
            self._input.setObjectName("ChatInputLowConfidence")
        else:
            self._input.setObjectName("ChatInput")
        self._input.style().unpolish(self._input)
        self._input.style().polish(self._input)
        self.focus_input()

    def set_voice_audit_hint(self, text: str) -> None:
        if text:
            self.set_stage_hint(text)
        elif not self._stage_hint.text():
            self.set_stage_hint("")

    def set_step_controls_enabled(self, enabled: bool):
        if hasattr(self, "_step_next_btn"):
            self._step_next_btn.setEnabled(enabled)

    def update_steps(self, steps: list, active_index: int = 0):
        descriptions = [
            s.get("desc") or s.get("description") or s.get("instruction") or s.get("action", "")
            for s in steps
        ]
        if self._l5_execution_mode and not self.is_l5_completed:
            plan_steps = [{"instruction": d} for d in descriptions]
            if self._l5_timeline.is_planning:
                if descriptions:
                    self.reset_l5_timeline(plan_steps)
            elif descriptions:
                # reset_plan no-ops when instruction list unchanged (preserves SSE/logs)
                self.reset_l5_timeline(plan_steps)
                self._l5_timeline.sync_active_index(active_index)
            total = len(descriptions)
            if total > 0:
                self._step_controls.show()
                cur = min(active_index + 1, total)
                self._step_progress_label.setText(f"L5 {cur} / {total}")
            elif self._l5_timeline.is_planning:
                self._step_controls.show()
                self._step_progress_label.setText("L5 规划中…")
            else:
                self._step_controls.hide()

    def _apply_l5_steps_layout(self) -> None:
        self._steps_list.hide()
        self._l5_timeline.show()

    @property
    def is_l5_completed(self) -> bool:
        return bool(getattr(self, "_l5_completed", False))

    def begin_l5_planning(self) -> None:
        """进入 L5：切步骤页、显示规划占位与停止/批准底栏。"""
        if self.is_l5_completed:
            self.finish_l5_execution()
        self.set_l5_execution_mode(True)
        self._l5_timeline.show_planning_placeholder()
        self._step_controls.show()
        self._step_progress_label.setText("L5 规划中…")

    def complete_l5_execution(self, *, outcome: str = "done") -> None:
        """L5 任务结束：保留时间线与步骤，底栏改为只读完成态。"""
        self._l5_completed = True
        self._l5_timeline.mark_completed(outcome)
        self._l5_execution_mode = True
        self._steps_title.setText("自动执行")
        self._steps_l5_badge.setText("L5")
        self._steps_l5_badge.show()
        self._apply_l5_steps_layout()
        self._switch_panel("steps")
        self._step_pause_btn.hide()
        self._step_stop_btn.hide()
        self._step_next_btn.setText("关闭")
        self._step_next_btn.show()
        self._step_controls.show()
        labels = {
            "done": ("L5 已完成", "L5 执行完成 · 步骤保留供回看"),
            "failed": ("L5 失败", "L5 执行失败 · 步骤保留供排查"),
            "cancelled": ("L5 已取消", "L5 已取消 · 步骤保留供回看"),
            "error": ("L5 错误", "L5 启动失败 · 已保留当前界面"),
        }
        prog, hint = labels.get(outcome, labels["done"])
        self._step_progress_label.setText(prog)
        self.set_stage_hint(hint)

    def finish_l5_execution(self) -> None:
        """硬重置 L5：恢复指引步骤 UI 并隐藏时间线。"""
        self._l5_completed = False
        self.set_l5_execution_mode(False)
        self._step_controls.hide()
        self.set_stage_hint("")

    def mirror_l5_steps_to_guide(self, steps: list) -> None:
        """L5 完成后同步步骤到指引列表，便于切换面板回看。"""
        descriptions = [
            s.get("desc")
            or s.get("description")
            or s.get("instruction")
            or ""
            for s in steps
        ]
        if not descriptions:
            return
        last_idx = max(0, len(descriptions) - 1)
        self._guide_steps.set_steps(descriptions, last_idx)
        self._steps_list.set_steps(descriptions, last_idx)

    def set_l5_execution_mode(self, enabled: bool) -> None:
        from core.user_settings import load_user_settings

        self._l5_execution_mode = bool(enabled)
        settings = load_user_settings()
        approve = (settings.get("shortcut_l5_approve") or "H").upper()
        stop = (settings.get("shortcut_l5_stop") or "J").upper()
        pause = (settings.get("shortcut_l5_pause") or "P").upper()
        if enabled:
            self._steps_title.setText("自动执行")
            self._steps_l5_badge.setText("L5")
            self._steps_l5_badge.show()
            self._apply_l5_steps_layout()
            self._step_pause_btn.show()
            self._step_next_btn.setText(f"批准 ({approve})")
            self._step_stop_btn.setText(f"停止 ({stop})")
            self._step_pause_btn.setText(f"暂停 ({pause})")
            self._step_stop_btn.show()
            self._switch_panel("steps")
        else:
            self._steps_title.setText("Step Tracking")
            self._steps_l5_badge.hide()
            self._l5_timeline.hide()
            self._steps_list.show()
            self._step_pause_btn.hide()
            self._step_next_btn.setText("下一步")
            self._step_stop_btn.setText("停止")
            self._step_stop_btn.hide()
            self._step_controls.hide()

    def reset_l5_timeline(self, steps: list) -> None:
        self._l5_timeline.reset_plan(steps)

    def show_l5_initial_screenshot(self, step_index: int, b64: str) -> None:
        self._l5_timeline.show_initial_screenshot(step_index, b64)

    def handle_l5_sse(self, event_type: str, data: dict) -> None:
        self._l5_timeline.handle_sse(event_type, data)
        idx = int(data.get("step_index", 1)) - 1
        if event_type == "step_start":
            self.set_l5_step_status(idx, "active")
        elif event_type == "step_done":
            self.set_l5_step_status(idx, "done")
        elif event_type == "step_failed":
            self.set_l5_step_status(idx, "failed")
        elif event_type == "step_blocked":
            self.set_l5_step_status(idx, "blocked")

    def append_l5_log(self, text: str) -> None:
        if not text:
            return
        idx = max(0, self._l5_timeline.active_index)
        level = "info"
        if text.startswith("[step_failed]") or "error" in text.lower():
            level = "error"
        elif text.startswith("[warn") or "blocked" in text.lower():
            level = "warn"
        self._l5_timeline.handle_sse(
            "log",
            {"step_index": idx + 1, "level": level, "message": text},
        )

    def l5_progress_label(self) -> str:
        total = self._l5_timeline.total_steps
        cur = max(0, self._l5_timeline.active_index) + 1
        if total <= 0:
            return "L5 执行中"
        inst = ""
        idx = self._l5_timeline.active_index
        if idx >= 0:
            inst = self._l5_timeline.step_instruction(idx)
        short = (inst[:24] + "…") if len(inst) > 24 else inst
        return f"L5 {cur}/{total} · {short}" if short else f"L5 {cur}/{total}"

    def set_l5_step_status(self, index: int, status: str) -> None:
        self._l5_timeline.set_step_status(index, status)

    def notify_l5_audit_compat(self, message: str) -> None:
        self.set_stage_hint("L5 自动执行中 · 审计按 L3 上报")

    def ensure_l5_consent(self, parent=None) -> bool:
        from core.user_settings import save_settings_fragment
        from ui.native.themed_message_box import themed_warning_consent

        data = load_user_settings()
        if data.get("l5_consent_accepted"):
            return True
        theme_id = getattr(self, "_ui_theme", None) or data.get("ui_theme", "current")
        accepted, dont_show = themed_warning_consent(
            parent or self,
            "L5 自动执行 — 知情确认",
            "您已选择 L5 自动执行模式。\n\n"
            "HAJIMI 将通过本机 Sidecar (server_A) 自动操作鼠标与键盘完成步骤。"
            "请确保屏幕无敏感内容，且可随时按 J 或「停止」终止任务。",
            theme_id=theme_id,
        )
        if not accepted:
            return False
        if dont_show:
            save_settings_fragment({"l5_consent_accepted": True})
        return True

    def should_stop_services_on_exit(self) -> bool:
        return self._stop_on_exit_cb.isChecked()

    def set_service_status(self, text: str):
        if text:
            self._service_status.setText(text)
        self._update_api_url_label()

    def focus_input(self):
        self._input.setFocus()
