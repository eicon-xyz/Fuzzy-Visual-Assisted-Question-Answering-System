# ui/main_widget.py
import os
import json

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QTimer, QEvent
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QGraphicsOpacityEffect,
)
from PyQt5.QtGui import QIcon

from config import (
    FRAMED_WINDOW,
    MEDIUM_WIDTH,
    MEDIUM_HEIGHT,
    COMPACT_WIDTH,
    COMPACT_HEIGHT,
    USE_NATIVE_UI,
    STOP_SERVICES_ON_EXIT,
    STARTUP_HEALTH_DELAY_MS,
    STARTUP_HEALTH_RETRY_MS,
    STARTUP_HEALTH_MAX_RETRIES,
)
from core.task_worker import TaskWorkerThread
from core.api_client import check_inspect_preflight, get_api_status_message
from core.service_manager import (
    start_backend_services,
    stop_backend_services,
    format_stop_summary,
)
from ui.overlay_anno import OverlayAnnoWindow
from ui.app_controller import AppController
from ui.native.medium_panel import MediumPanel
from ui.native.compact_bar import CompactBar
from ui.native.suspension_dialog import SuspensionDialog
from core.inspect_worker import InspectWorkerThread
from core.relocate_worker import RelocateWorkerThread
from ui.native.prepare_step_dialog import PrepareStepDialog
from ui.native.resize_grip import WindowResizeHandler
from ui.native.motion import (
    animate_fade_in,
    resize_keep_bottom_right,
    animate_mode_transition,
)
from ui.native.window_state import (
    load_window_state,
    save_window_state,
    apply_state_to_window,
)

_THEME_PATH = os.path.join(os.path.dirname(__file__), "native", "theme.qss")


def _load_theme(app: QApplication):
    if os.path.isfile(_THEME_PATH):
        with open(_THEME_PATH, encoding="utf-8") as f:
            app.setStyleSheet(f.read())


class MainWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HAJIMI 智能桌面助手")
        self.setAttribute(Qt.WA_DeleteOnClose)

        if USE_NATIVE_UI:
            _load_theme(QApplication.instance())
            from ui.native.fonts import apply_app_font
            apply_app_font(QApplication.instance())

        self._mode = "medium"
        self._medium_size = [MEDIUM_WIDTH, MEDIUM_HEIGHT]
        self._mode_switching = False
        self._prepare_hint = ""
        self._prepare_desc = ""
        self.overlay = OverlayAnnoWindow()
        self.worker = TaskWorkerThread(self)
        self.inspect_worker = InspectWorkerThread(self)
        self.relocate_worker = RelocateWorkerThread(self)

        if USE_NATIVE_UI:
            self._init_native_ui()
        else:
            self._init_web_ui()

        self._apply_window_flags()
        if USE_NATIVE_UI:
            self._restore_window_state()
        else:
            self._position_bottom_right()

    def _restore_window_state(self):
        state = load_window_state()
        if state:
            self._medium_size = [state.medium_width, state.medium_height]
            apply_state_to_window(self, state)
            if state.x is None or state.y is None:
                self._position_bottom_right()
            if state.last_mode == "compact":
                QTimer.singleShot(0, lambda: self.switch_to_compact(animated=False))
            else:
                self.medium_panel._update_mode_pills_visibility()
        else:
            self.resize(MEDIUM_WIDTH, MEDIUM_HEIGHT)
            self._position_bottom_right()

    def _state_save_timer(self):
        if not hasattr(self, "_window_state_timer"):
            self._window_state_timer = QTimer(self)
            self._window_state_timer.setSingleShot(True)
            self._window_state_timer.timeout.connect(self._save_window_state)
        return self._window_state_timer

    def _save_window_state(self):
        if not USE_NATIVE_UI:
            return
        save_window_state(
            medium_width=self._medium_size[0],
            medium_height=self._medium_size[1],
            x=self.x(),
            y=self.y(),
            last_mode=self._mode,
        )

    def _apply_window_flags(self):
        if FRAMED_WINDOW:
            self.resize(MEDIUM_WIDTH, MEDIUM_HEIGHT)
            return

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if not USE_NATIVE_UI:
            self.resize(MEDIUM_WIDTH, MEDIUM_HEIGHT)

    def _init_native_ui(self):
        self.controller = AppController(self.worker, main_window=self)
        self.suspension_dialog = SuspensionDialog(self)
        self.prepare_step_dialog = PrepareStepDialog(self)

        self.stack = QStackedWidget(self)
        self.medium_panel = MediumPanel()
        self.compact_bar = CompactBar()
        self.stack.addWidget(self.medium_panel)
        self.stack.addWidget(self.compact_bar)
        self.stack.setCurrentWidget(self.medium_panel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 14)
        layout.addWidget(self.stack)

        self._resize_handler = WindowResizeHandler(
            self, lambda: self.stack, lambda: self._mode == "medium"
        )
        self.setMouseTracking(True)
        self._install_resize_tracking()

        self._wire_controller()
        self._wire_native_widgets()
        self._wire_inspect_worker()
        self._wire_relocate_worker()
        self._setup_tray()
        self._check_api_on_startup()

    def _install_resize_tracking(self):
        """Forward edge mouse events from panel children to resize handler."""
        self.stack.setMouseTracking(True)
        self.medium_panel.setMouseTracking(True)
        for w in (self.medium_panel,):
            w.installEventFilter(self)
            for child in w.findChildren(QWidget):
                child.setMouseTracking(True)
                child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if (
            USE_NATIVE_UI
            and hasattr(self, "_resize_handler")
            and self._mode == "medium"
        ):
            et = event.type()
            if et == QEvent.MouseButtonPress:
                if self._resize_handler.try_press_global(
                    event.globalPos(), event.button()
                ):
                    return True
            elif et == QEvent.MouseMove:
                if self._resize_handler.try_move_global(event.globalPos()):
                    return True
            elif et == QEvent.MouseButtonRelease:
                if self._resize_handler.try_release_global(
                    event.globalPos(), event.button()
                ):
                    return True
        return super().eventFilter(obj, event)

    def _wire_relocate_worker(self):
        w = self.relocate_worker
        w.sig_relocate_success.connect(self._on_relocate_success)
        w.sig_relocate_success.connect(self.controller.on_relocate_success)
        w.sig_relocate_error.connect(self._on_relocate_error)
        w.sig_relocate_error.connect(self.controller.on_relocate_error)
        w.sig_progress.connect(
            lambda _pct, label: self.controller.message_added.emit(label, "system")
        )
        w.finished.connect(self._on_relocate_finished)

    def _on_relocate_success(self, _data):
        self.prepare_step_dialog.set_busy(False)
        self.medium_panel.hide_prepare_banner()

    def _on_relocate_error(self, _msg):
        self.prepare_step_dialog.set_busy(False)

    def _on_relocate_finished(self):
        self.prepare_step_dialog.set_busy(False)

    def _on_prepare_step(self, hint: str, desc: str):
        self._prepare_hint = hint
        self._prepare_desc = desc
        self.prepare_step_dialog.show_hint(hint, desc)

    def _on_prepare_dismissed(self, desc: str):
        self.medium_panel.show_prepare_banner(desc or self._prepare_desc or "当前步骤")

    def _on_prepare_banner(self):
        self.prepare_step_dialog.show_hint(self._prepare_hint, self._prepare_desc)

    def _on_prepare_confirmed(self):
        if self.relocate_worker.isRunning():
            self.controller.message_added.emit(
                "正在分析新画面，请稍候…", "system"
            )
            return
        if not self.controller.task_id:
            return
        step_index = self.controller.current_step_index + 1
        self.prepare_step_dialog.set_busy(True)
        self.controller.status_updated.emit("processing", "重新定位中…")
        self.relocate_worker.request_relocate(self.controller.task_id, step_index)

    def _wire_inspect_worker(self):
        w = self.inspect_worker
        w.sig_inspect_success.connect(self.controller.on_inspect_success)
        w.sig_inspect_error.connect(self.controller.on_inspect_error)
        w.sig_progress.connect(self._on_inspect_progress)
        w.finished.connect(self._on_inspect_finished)

    def _wire_controller(self):
        c = self.controller
        c.message_added.connect(self.medium_panel.append_message)
        c.steps_updated.connect(self.medium_panel.update_steps)
        c.status_updated.connect(self.medium_panel.set_status_badge)
        c.status_updated.connect(self._on_status_updated)
        c.blueprint_updated.connect(self.medium_panel.render_blueprint)
        c.overlay_updated.connect(self.overlay.update_annotations)
        c.overlay_cleared.connect(self.overlay.clear_annotations)
        c.inspect_updated.connect(self._on_inspect_updated)
        c.inspect_cleared.connect(self.overlay.clear_inspect_annotations)
        c.inspect_status.connect(self.medium_panel.set_inspect_status)
        c.suspension_requested.connect(self.suspension_dialog.show_message)
        c.suspension_hidden.connect(self.suspension_dialog.hide)
        c.prepare_step_requested.connect(self._on_prepare_step)
        c.mode_medium_requested.connect(lambda: self.switch_to_medium(animated=True))
        c.mode_compact_requested.connect(lambda: self.switch_to_compact(animated=True))
        self.suspension_dialog.resolved.connect(c.resolve_suspension)
        self.prepare_step_dialog.confirmed.connect(self._on_prepare_confirmed)
        self.prepare_step_dialog.dismissed.connect(self._on_prepare_dismissed)
        self.medium_panel.prepare_banner_clicked.connect(self._on_prepare_banner)
        self.overlay.sig_target_clicked.connect(c.on_target_area_clicked)

        self.worker.sig_progress.connect(self._on_task_progress)

    def _on_status_updated(self, status: str, _label: str):
        busy = status == "processing"
        self.medium_panel.set_input_enabled(not busy)
        self.compact_bar.set_input_enabled(not busy)

    def _on_task_progress(self, _pct: int, label: str):
        self.medium_panel.set_stage_hint(label)

    def _wire_native_widgets(self):
        p = self.medium_panel
        b = self.compact_bar
        p.send_clicked.connect(self._on_submit_query)
        b.submit_query.connect(self._on_submit_query)
        p.next_clicked.connect(self.controller.advance_step)
        p.prev_clicked.connect(self.controller.prev_step)
        p.compact_requested.connect(self.switch_to_compact)
        p.drag_requested.connect(self.controller.begin_window_drag)
        p.inspect_requested.connect(self._on_inspect_requested)
        p.inspect_exit_requested.connect(self.controller.exit_inspect_mode)
        p.start_services_requested.connect(self._on_start_services)
        p.stop_services_requested.connect(self._on_stop_services)
        b.expand_requested.connect(self.switch_to_medium)
        b.drag_requested.connect(self.controller.begin_window_drag)
        p.height_resize_drag.connect(self._resize_window_height)
        p.quit_requested.connect(self._quit_application)

    def on_medium_resized(self):
        self._medium_size = [self.width(), self.height()]
        self.medium_panel._update_mode_pills_visibility()
        self._state_save_timer().start(500)

    def _resize_window_height(self, delta: int):
        if self._mode != "medium" or delta == 0:
            return
        g = self.geometry()
        max_w, max_h = self._resize_handler._max_size()
        min_h = 300
        new_h = max(min_h, min(max_h, g.height() + delta))
        actual = new_h - g.height()
        if actual == 0:
            return
        self.setGeometry(g.x(), g.y() - actual, g.width(), new_h)
        self.on_medium_resized()

    def paintEvent(self, event):
        super().paintEvent(event)
        if hasattr(self, "_resize_handler") and USE_NATIVE_UI:
            from PyQt5.QtGui import QPainter
            p = QPainter(self)
            self._resize_handler.paint_hover(p)
            p.end()

    def mousePressEvent(self, event):
        if (
            USE_NATIVE_UI
            and hasattr(self, "_resize_handler")
            and self._resize_handler.mouse_press(event)
        ):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            USE_NATIVE_UI
            and hasattr(self, "_resize_handler")
            and self._resize_handler.mouse_move(event)
        ):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            USE_NATIVE_UI
            and hasattr(self, "_resize_handler")
            and self._resize_handler.mouse_release(event)
        ):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _apply_size_bottom_right(self, w: int, h: int, animated: bool = False):
        resize_keep_bottom_right(self, w, h, self, animated=animated)

    def _check_api_on_startup(self):
        if not hasattr(self, "controller"):
            return
        self._startup_health_attempt = 0
        QTimer.singleShot(STARTUP_HEALTH_DELAY_MS, self._run_startup_health_check)

    def _run_startup_health_check(self):
        if not hasattr(self, "controller"):
            return
        text, msg_type = get_api_status_message()
        is_error = "danger" in msg_type
        if not is_error or self._startup_health_attempt >= STARTUP_HEALTH_MAX_RETRIES:
            self.controller.message_added.emit(text, msg_type)
            return
        self._startup_health_attempt += 1
        QTimer.singleShot(STARTUP_HEALTH_RETRY_MS, self._run_startup_health_check)

    def _on_submit_query(self, text: str):
        self.controller.submit_query(text)

    def _on_inspect_requested(self):
        if self.inspect_worker.isRunning():
            self.medium_panel.set_inspect_status(
                "检测进行中，CPU 约 2–4 分钟，请勿重复点击…"
            )
            return

        ok, reason = check_inspect_preflight()
        if not ok:
            self.medium_panel.set_inspect_status(f"检验失败: {reason}")
            self.controller.message_added.emit(f"检验失败: {reason}", "system danger")
            return

        if not self.controller.run_inspect():
            return
        self.overlay.clear_annotations()
        self.medium_panel.set_inspect_busy(True)
        self.inspect_worker.start()

    def _on_inspect_finished(self):
        self.medium_panel.set_inspect_busy(False)

    def _on_inspect_updated(self, items, meta):
        self.overlay.update_inspect_annotations(items)

    def _on_inspect_progress(self, pct, label):
        self.medium_panel.set_inspect_status(label)

    def _on_start_services(self):
        try:
            start_backend_services()
            self.medium_panel.set_service_status(
                "已清理旧进程并启动新窗口；请等待 OmniParser「Omniparser initialized」"
                "（约 1–2 分钟）后再提问。"
            )
            self.controller.message_added.emit(
                "已停止旧后端并重新启动 OmniParser + A 端…", "system"
            )
        except Exception as exc:
            self.medium_panel.set_service_status(f"启动失败: {exc}")
            self.controller.message_added.emit(f"启动后端失败: {exc}", "system danger")

    def _on_stop_services(self):
        result = stop_backend_services()
        summary = format_stop_summary(result)
        self.medium_panel.set_service_status(f"已停止: {summary}")
        self.controller.message_added.emit(f"已停止后端服务: {summary}", "system")

    def _shutdown_workers(self, max_wait_ms: int = 2000):
        for name in ("worker", "inspect_worker"):
            w = getattr(self, name, None)
            if w and w.isRunning():
                w.terminate()
                w.wait(max_wait_ms)

    def _stop_backend_if_enabled(self):
        if not STOP_SERVICES_ON_EXIT:
            return
        if not hasattr(self, "medium_panel"):
            return
        if not self.medium_panel.should_stop_services_on_exit():
            return
        summary = format_stop_summary(stop_backend_services())
        print(f"[HAJIMI] 退出时停止后端: {summary}")

    def _quit_application(self):
        self._save_window_state()
        self._shutdown_workers()
        self._stop_backend_if_enabled()
        if hasattr(self, "overlay"):
            self.overlay.close()
        if hasattr(self, "tray"):
            self.tray.hide()
        QApplication.quit()

    def switch_to_medium(self, animated: bool = True):
        if self._mode == "medium":
            self.medium_panel.focus_input()
            return
        if self._mode_switching:
            return

        outgoing = self.compact_bar
        incoming = self.medium_panel
        w, h = self._medium_size
        self._mode = "medium"
        self._resize_handler.set_enabled(True)

        if not animated:
            self._apply_size_bottom_right(w, h, animated=False)
            self.stack.setCurrentWidget(self.medium_panel)
            self.medium_panel.focus_input()
            self.medium_panel._update_mode_pills_visibility()
            self._save_window_state()
            return

        self._mode_switching = True
        self.setEnabled(False)

        def done():
            outgoing.setGraphicsEffect(None)
            incoming.setGraphicsEffect(None)
            outgoing.update()
            incoming.update()
            self._mode_switching = False
            self.setEnabled(True)
            self.medium_panel.focus_input()
            self.medium_panel._update_mode_pills_visibility()
            self._save_window_state()

        animate_mode_transition(
            self,
            self.stack,
            outgoing,
            incoming,
            w,
            h,
            self,
            on_complete=done,
        )

    def switch_to_compact(self, animated: bool = True):
        if self._mode == "compact":
            return
        if self._mode_switching:
            return

        if self._mode == "medium":
            self._medium_size = [self.width(), self.height()]

        outgoing = self.medium_panel
        incoming = self.compact_bar
        w = self.width() if self.width() > 0 else COMPACT_WIDTH
        h = COMPACT_HEIGHT
        self._mode = "compact"
        self._resize_handler.set_enabled(False)

        if not animated:
            self._apply_size_bottom_right(w, h, animated=False)
            self.stack.setCurrentWidget(self.compact_bar)
            self.compact_bar.focus_input()
            self._save_window_state()
            return

        self._mode_switching = True
        self.setEnabled(False)

        def done():
            outgoing.setGraphicsEffect(None)
            incoming.setGraphicsEffect(None)
            outgoing.update()
            incoming.update()
            self._mode_switching = False
            self.setEnabled(True)
            self.compact_bar.focus_input()
            self._save_window_state()

        animate_mode_transition(
            self,
            self.stack,
            outgoing,
            incoming,
            w,
            h,
            self,
            on_complete=done,
        )

    def _animate_switch(self, target_widget):
        """Legacy hook — use switch_to_medium/compact instead."""
        self.stack.setCurrentWidget(target_widget)
        animate_fade_in(target_widget, self)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("HAJIMI 智能桌面助手")

        menu = QMenu()
        show_action = QAction("显示面板", self)
        show_action.triggered.connect(self._show_from_tray)
        compact_action = QAction("紧凑模式", self)
        compact_action.triggered.connect(self.switch_to_compact)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit_application)
        menu.addAction(show_action)
        menu.addAction(compact_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _show_from_tray(self):
        self.show()
        self.raise_()
        self.switch_to_medium()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_from_tray()

    def _init_web_ui(self):
        from PyQt5.QtCore import QUrl
        from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
        from PyQt5.QtWebChannel import QWebChannel
        from PyQt5.QtGui import QColor
        from ui.bridge_web import Bridge

        self.bridge = Bridge(self.worker, main_window=self)
        self.bridge.sig_add_message.connect(self._on_add_message)
        self.bridge.sig_update_steps.connect(self._on_update_steps)
        self.bridge.sig_update_status.connect(self._on_update_status)
        self.bridge.sig_update_overlay.connect(self.overlay.update_annotations)
        self.bridge.sig_clear_overlay.connect(self.overlay.clear_annotations)
        self.bridge.sig_render_blueprint.connect(self._on_render_blueprint)
        self.bridge.sig_show_suspension.connect(self._on_show_suspension)
        self.bridge.sig_hide_suspension.connect(self._on_hide_suspension)
        self.overlay.sig_target_clicked.connect(self.bridge.onTargetAreaClicked)

        self.web_view = QWebEngineView(self)
        self.web_view.setPage(QWebEnginePage(self))
        self.web_view.setZoomFactor(1.0)
        self.web_view.setStyleSheet("background: transparent;")
        self.web_view.page().setBackgroundColor(QColor(0, 0, 0, 0))

        self.channel = QWebChannel(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        html_path = os.path.join(os.path.dirname(__file__), "web", "index.html")
        self.web_view.load(QUrl.fromLocalFile(html_path))
        self.web_view.page().loadFinished.connect(self._on_load_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web_view)

    def _position_bottom_right(self, margin=60):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        area = screen.availableGeometry()
        self.move(
            area.right() - self.width() - margin,
            area.bottom() - self.height() - margin,
        )

    def _on_load_finished(self):
        js = """
        (function() {
            function bindBridge() {
                if (typeof qt === 'undefined' || !qt.webChannelTransport) return;
                new QWebChannel(qt.webChannelTransport, function(channel) {
                    window.pyBridge = channel.objects.pyBridge;
                    if (typeof window.initDesktopHost === 'function') {
                        window.initDesktopHost();
                    }
                });
            }
            if (typeof QWebChannel === 'undefined') {
                var script = document.createElement('script');
                script.src = 'qrc:///qtwebchannel/qwebchannel.js';
                script.onload = bindBridge;
                document.head.appendChild(script);
            } else {
                bindBridge();
            }
        })();
        """
        self.web_view.page().runJavaScript(js)

    def _on_add_message(self, text, msg_type):
        escaped = json.dumps(text)
        js = f'window.addMessage({escaped}, {json.dumps(msg_type)});'
        self.web_view.page().runJavaScript(js)

    def _on_update_steps(self, steps, index):
        steps_json = json.dumps(steps, ensure_ascii=False)
        js = f'window.updateSteps({steps_json}, {index});'
        self.web_view.page().runJavaScript(js)

    def _on_update_status(self, status, label):
        js = f'window.updateStatus({json.dumps(status)}, {json.dumps(label)});'
        self.web_view.page().runJavaScript(js)

    def _on_render_blueprint(self, steps, index):
        steps_json = json.dumps(steps, ensure_ascii=False)
        js = f'window.renderBlueprintFromPython({steps_json}, {index});'
        self.web_view.page().runJavaScript(js)

    def _on_show_suspension(self, message):
        js = f'window.showSuspensionModal({json.dumps(message)});'
        self.web_view.page().runJavaScript(js)

    def _on_hide_suspension(self):
        self.web_view.page().runJavaScript("window.hideSuspensionModal();")

    def closeEvent(self, event):
        self._save_window_state()
        self._shutdown_workers()
        self._stop_backend_if_enabled()
        if hasattr(self, "overlay"):
            self.overlay.close()
        if hasattr(self, "tray"):
            self.tray.hide()
        event.accept()
