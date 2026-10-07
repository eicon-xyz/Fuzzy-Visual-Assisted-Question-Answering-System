# ui/main_widget.py
import os

from PyQt5.QtCore import Qt, QRect, QTimer, QEvent
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QAction,
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
    BACKEND_POLL_DISCONNECTED_MS,
    BACKEND_POLL_CONNECTED_MS,
    L5_API_URL,
    DEMO_KEY,
)
from core.bc_signals import BCIntegrationSignals
from core.repo_paths import (
    clear_shadow_client_modules,
    ensure_repo_root_on_path,
    resolve_repo_root,
)
from core.execute_worker import ExecuteWorkerThread
from core.api_client import get_api_status_message
from core.user_settings import (
    apply_user_settings,
    load_user_settings,
    load_voice_settings,
    save_settings_fragment,
)
from core.env_sync import sync_l5_sidecar_env
from core.service_manager import (
    restart_l5_sidecar,
    stop_backend_services,
    format_stop_summary,
)
from ui.app_controller import AppController
from ui.native.medium_panel import MediumPanel
from ui.native.compact_bar import CompactBar
from core.backend_health_worker import BackendHealthWorker
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
from ui.native.window_clip import apply_shell_mask, clamp_geometry_to_screen
from ui.native.theme_manager import get_theme_manager
from ui.native.shell_appearance import (
    AppearanceSettings,
    SHELL_STYLES,
    appearance_scheme_label,
    is_luxury_theme,
    is_orange_cat_theme,
)
from ui.native.orange_cat.splash_controller import OrangeCatSplashController
from ui.native.luxury.qss import LUXURY_BG_MODES
from ui.native.luxury.title import script_font_labels
from ui.native.title_art import TITLE_ART_MODES
from ui.native.nav_icons import svg_icon


class MainWidget(QWidget):
    def __init__(self, startup_hints=None):
        super().__init__()
        self._startup_hints = list(startup_hints or [])
        self.setWindowTitle("HAJIMI 智能桌面助手")
        self.setAttribute(Qt.WA_DeleteOnClose)

        if USE_NATIVE_UI:
            from ui.native.fonts import apply_app_font
            apply_app_font(QApplication.instance())

        self._mode = "medium"
        self._medium_size = [MEDIUM_WIDTH, MEDIUM_HEIGHT]
        self._compact_size = [COMPACT_WIDTH, COMPACT_HEIGHT]
        self._size_before_settings = None
        self._geometry_anim = None
        self._mode_switching = False
        self.execute_worker = ExecuteWorkerThread(self)
        self.backend_health_worker = BackendHealthWorker(self)
        self._backend_poll_timer = QTimer(self)
        self._backend_poll_timer.setSingleShot(True)
        self._last_backend_status_key = ""
        self._backend_connected = False

        self._init_native_ui()

        self._apply_window_flags()
        self._restore_window_state()

    def _restore_window_state(self):
        state = load_window_state()
        if state:
            self._medium_size = [state.medium_width, state.medium_height]
            self._compact_size = [state.compact_width, COMPACT_HEIGHT]
            apply_state_to_window(self, state)
            self._clamp_medium_width_to_topbar()
            if state.migrated_from_legacy:
                self._state_save_timer().start(0)
            if state.x is None or state.y is None:
                self._position_bottom_right()
            if state.last_mode == "compact":
                QTimer.singleShot(0, lambda: self.switch_to_compact(animated=False))
            else:
                self.medium_panel._update_mode_pills_visibility()
        else:
            self.resize(MEDIUM_WIDTH, MEDIUM_HEIGHT)
            self._clamp_medium_width_to_topbar()
            self._position_bottom_right()

    def _clamp_medium_width_to_topbar(self) -> None:
        if not hasattr(self, "medium_panel"):
            return
        min_w = self.topbar_min_width(include_panel_sub=False)
        mw = max(self._medium_size[0], min_w)
        if mw != self._medium_size[0]:
            self._medium_size[0] = mw
        if self._mode != "medium":
            return
        w, h = self.width(), self.height()
        if w < min_w:
            self._apply_size_bottom_right(min_w, h, animated=False)

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
            compact_width=self._compact_size[0],
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
        self._bc_signals = BCIntegrationSignals(self)
        self._shared_state = {"voice_settings": load_voice_settings()}
        self._c_controller = None
        self._asr_listening = False
        self._c_load_error = ""
        self._c_degraded_notified = False
        self._asr_timeout_timer = QTimer(self)
        self._asr_timeout_timer.setSingleShot(True)
        self._asr_timeout_timer.timeout.connect(self._on_asr_timeout)
        self._asr_nudge_timer = QTimer(self)
        self._asr_nudge_timer.setSingleShot(True)
        self._asr_nudge_timer.timeout.connect(self._on_asr_nudge)

        self.controller = AppController(
            execute_worker=self.execute_worker,
            main_window=self,
            bc_signals=self._bc_signals,
            voice_settings=self._shared_state["voice_settings"],
        )

        self.stack = QStackedWidget(self)
        self.medium_panel = MediumPanel()
        self.compact_bar = CompactBar()
        self.stack.addWidget(self.medium_panel)
        self.stack.addWidget(self.compact_bar)
        self.stack.setCurrentWidget(self.medium_panel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

        self._resize_handler = WindowResizeHandler(
            self,
            lambda: self.stack,
            lambda: self._mode == "medium",
            lambda: self._mode == "compact",
        )
        self.setMouseTracking(True)
        self._install_resize_tracking()

        self._prepare_lazy_voice_ui()
        self._wire_controller()
        self._wire_native_widgets()
        self._wire_backend_health_worker()
        self._setup_tray()
        self._check_api_on_startup()
        mgr = get_theme_manager(QApplication.instance())
        mgr.register_shell(self.medium_panel, compact=False)
        mgr.register_shell(self.compact_bar, compact=True)
        self._orange_cat_splash = OrangeCatSplashController(self)
        self._apply_native_appearance()

    def _prepare_lazy_voice_ui(self) -> None:
        """启动时不加载 C，仅准备麦克风；首次点击再加载。"""
        if os.environ.get("HAJIMI_C_ENABLED", "1") != "1":
            self.medium_panel.set_c_integration_status("C 端已禁用（HAJIMI_C_ENABLED=0）")
            self.medium_panel.set_mic_enabled(False)
            return
        voice = self._shared_state.get("voice_settings") or load_voice_settings()
        asr_on = voice.get("asr_enabled", True)
        self.medium_panel.set_mic_enabled(bool(asr_on))
        self.medium_panel.set_c_integration_status(
            "语音模块将在首次点击麦克风时加载（加速启动）"
        )

    def _ensure_c_integration(self) -> bool:
        """懒加载 C；成功返回 True。"""
        if self._c_controller is not None and not self._c_load_error:
            return True
        self._init_c_integration()
        return self._c_controller is not None and not self._c_load_error

    def _init_c_integration(self) -> None:
        if os.environ.get("HAJIMI_C_ENABLED", "1") != "1":
            return
        if self._c_controller is not None and not self._c_load_error:
            return
        try:
            ensure_repo_root_on_path()
            clear_shadow_client_modules()
            root = resolve_repo_root()
            client_dir = root / "client"
            if not client_dir.is_dir():
                msg = "client/ 目录未找到，语音集成已跳过"
                print(f"[C] {msg}")
                self._c_load_error = msg
                self.medium_panel.set_c_integration_status(msg)
                return
            from client.integration.controller import VoiceIntegrationController

            voice = self._shared_state.get("voice_settings") or load_voice_settings()
            self._c_load_error = ""
            self._c_controller = VoiceIntegrationController(
                server_url=L5_API_URL,
                demo_key=DEMO_KEY,
                voice_settings=voice,
            )
            self._c_controller.start()
            self._c_controller.bind_to(self._bc_signals, self._shared_state)
            print("[C] integration OK — VoiceIntegrationController signals bound")
            if voice.get("asr_enabled", True):
                self.medium_panel.set_mic_enabled(True)
            QTimer.singleShot(200, self._request_c_health_check)
        except Exception as exc:
            msg = f"C 端加载失败: {exc}"
            print(f"[C] integration unavailable: {exc}")
            self._c_load_error = msg
            self._c_controller = None
            if hasattr(self, "medium_panel"):
                self.medium_panel.set_c_integration_status(
                    f"{msg}。请运行: python client/voice_setup.py"
                )

    def _request_c_health_check(self) -> None:
        if self._bc_signals:
            self._bc_signals.health_check_request.emit()

    def _on_c_health_result(self, health) -> None:
        if health is None:
            return
        if hasattr(health, "asr_available"):
            asr_ok = bool(health.asr_available)
            tts_ok = bool(health.tts_available)
            overall = health.overall
            queue_depth = int(getattr(health, "queue_depth", 0) or 0)
        else:
            asr_ok = bool(health.get("asr_available"))
            tts_ok = bool(health.get("tts_available"))
            overall = health.get("overall", "")
            queue_depth = int(health.get("queue_depth") or 0)

        voice = self._shared_state.get("voice_settings") or {}
        asr_on = voice.get("asr_enabled", True)
        # 懒加载：未加载 C 时仍允许点 mic；已加载则保持可点
        self.medium_panel.set_mic_enabled(bool(asr_on))
        health_text = (
            f"C 端：{overall or 'unknown'}"
            f" | ASR={'可用' if asr_ok else '不可用'}"
            f" | TTS={'可用' if tts_ok else '不可用'}"
        )
        if not asr_ok and self._c_controller and not self._c_load_error:
            health_text += "（仍可尝试录音；若失败请检查 pyaudio / 引擎设置）"
        elif not asr_ok and not self._c_load_error:
            health_text += "。请运行: pip install -r client/requirements.txt（含 pyaudio）"
        self.medium_panel.set_c_integration_status(health_text)
        if tts_ok and voice.get("tts_enabled", True):
            self.medium_panel.set_speaker_playing(False)
        if queue_depth > 50:
            self.medium_panel.set_voice_audit_hint(f"离线队列积压：{queue_depth} 条")
        if overall == "degraded" and not getattr(self, "_c_degraded_notified", False):
            if asr_ok and tts_ok:
                self.controller.message_added.emit(
                    "L5 Sidecar 未连接，语音功能正常；审计上报将离线排队",
                    "system",
                )
            else:
                self.controller.message_added.emit("部分 C 端服务降级", "system")
            self._c_degraded_notified = True
        elif overall == "unhealthy":
            self.controller.message_added.emit(
                "C 端服务异常，语音功能不可用", "system danger"
            )

    def _on_tts_status(self, status: str, text: str, _queue_depth: int) -> None:
        self.medium_panel.set_speaker_playing(status == "playing")
        if status == "playing" and text:
            preview = text if len(text) <= 24 else text[:24] + "…"
            self.medium_panel.set_stage_hint(f"正在播报：{preview}")
        elif status in ("idle", "stopped", "error"):
            if self.medium_panel._stage_hint.text().startswith("正在播报"):
                self.medium_panel.set_stage_hint("")

    def _on_audit_status(
        self, status: str, _batch_size: int, queue_depth: int, error
    ) -> None:
        if queue_depth > 50:
            self.medium_panel.set_voice_audit_hint(f"离线队列积压：{queue_depth} 条")
        elif status == "failed" and error:
            print(f"[audit] batch failed: {error}")

    def _on_config_updated(self, config_dict: dict) -> None:
        version = config_dict.get("version", "?")
        self.controller.message_added.emit(f"配置已更新至 {version}", "system")
        interval = config_dict.get("config_pull_interval_min")
        if interval and self._c_controller and hasattr(self._c_controller, "_config_poller"):
            poller = self._c_controller._config_poller
            if poller:
                poller.set_interval(interval)
        try:
            from core import api_client

            api_client.reload_client_config()
        except Exception:
            pass

    def _shutdown_c_integration(self) -> None:
        if self._c_controller:
            try:
                self._c_controller.shutdown()
            except Exception:
                pass
            self._c_controller = None

    def _should_use_pill_mask(self) -> bool:
        return (
            self._mode == "compact"
            and not self._mode_switching
            and self.height() <= COMPACT_HEIGHT + 4
        )

    def _apply_window_mask(self) -> None:
        if not USE_NATIVE_UI or FRAMED_WINDOW:
            return
        apply_shell_mask(self, pill=self._should_use_pill_mask())

    def _dismiss_drawer_overlay(self) -> None:
        if hasattr(self, "medium_panel"):
            self.medium_panel.force_dismiss_drawer()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_window_mask()
        if hasattr(self, "_orange_cat_splash"):
            self._orange_cat_splash.on_window_shown(self._current_ui_theme())

    def _current_ui_theme(self) -> str:
        if hasattr(self, "medium_panel"):
            return getattr(self.medium_panel, "_ui_theme", "current")
        return load_user_settings().get("ui_theme", "current")

    def _sync_orange_cat_chrome(
        self,
        ui_theme: str,
        appearance: AppearanceSettings,
        *,
        avatar_data: dict | None = None,
    ) -> None:
        from ui.native.orange_cat.image_pool import apply_avatar_settings

        apply_avatar_settings(avatar_data)
        if hasattr(self, "compact_bar"):
            self.compact_bar.apply_orange_cat_theme(is_orange_cat_theme(ui_theme))
        if hasattr(self, "medium_panel"):
            self.medium_panel.refresh_orange_cat_avatars()
        if hasattr(self, "_orange_cat_splash"):
            self._orange_cat_splash.apply_theme(ui_theme, appearance)

    def _apply_native_appearance(self, settings: dict | None = None) -> None:
        data = settings if settings is not None else load_user_settings()
        ui_theme = data.get("ui_theme", "current")
        appearance = AppearanceSettings.from_user_settings(data)
        get_theme_manager().apply(ui_theme, appearance)
        self._sync_orange_cat_chrome(ui_theme, appearance, avatar_data=data)
        if hasattr(self, "medium_panel"):
            self.medium_panel.apply_appearance(appearance, ui_theme=ui_theme)
        if hasattr(self, "stack"):
            self.stack.update()
        if hasattr(self, "medium_panel"):
            self.medium_panel.update()

    def _apply_appearance_preview(self, data: dict) -> None:
        ui_theme = data.get("ui_theme", "current")
        appearance = AppearanceSettings.from_user_settings(data)
        get_theme_manager().apply(ui_theme, appearance)
        self._sync_orange_cat_chrome(ui_theme, appearance, avatar_data=data)
        if hasattr(self, "medium_panel"):
            self.medium_panel.apply_appearance(appearance, ui_theme=ui_theme)
            if self.medium_panel.current_panel() == "settings":
                self.medium_panel._schedule_settings_size()
        if hasattr(self, "stack"):
            self.stack.update()
        if hasattr(self, "medium_panel"):
            self.medium_panel.update()
        self._apply_window_mask()

    def _install_resize_tracking(self):
        """Forward edge mouse events from panel children to resize handler."""
        self.stack.setMouseTracking(True)
        self.medium_panel.setMouseTracking(True)
        self.compact_bar.setMouseTracking(True)
        for w in (self.medium_panel, self.compact_bar):
            w.installEventFilter(self)
            for child in w.findChildren(QWidget):
                child.setMouseTracking(True)
                child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and hasattr(self, "controller"):
            key = event.text().upper()
            if key and self.controller.handle_l5_hotkey(key):
                return True
        if (
            USE_NATIVE_UI
            and hasattr(self, "_resize_handler")
            and self._mode in ("medium", "compact")
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

    def _wire_backend_health_worker(self):
        w = self.backend_health_worker
        w.sig_ready.connect(self._on_backend_health_ready)
        w.finished.connect(self._schedule_backend_health_poll)
        self._backend_poll_timer.timeout.connect(self._trigger_backend_health_poll)

    def _wire_controller(self):
        c = self.controller
        c.message_added.connect(self.medium_panel.append_message)
        c.steps_updated.connect(self.medium_panel.update_steps)
        c.status_updated.connect(self.medium_panel.set_status_badge)
        c.status_updated.connect(self._on_status_updated)
        c.mode_compact_requested.connect(lambda: self.switch_to_compact(animated=True))

        self.execute_worker.sig_progress.connect(self._on_task_progress)
        c.l5_compact_status_updated.connect(self._on_l5_compact_status)

        if self._bc_signals:
            self._bc_signals.asr_result.connect(self._on_asr_session_finished)
            self._bc_signals.asr_result.connect(self.controller.on_asr_result)
            self._bc_signals.tts_status.connect(self._on_tts_status)
            self._bc_signals.audit_status.connect(self._on_audit_status)
            self._bc_signals.config_updated.connect(self._on_config_updated)
            self._bc_signals.health_result.connect(self._on_c_health_result)
            self.medium_panel.mic_clicked.connect(self._on_mic_clicked)

    def _asr_hint_text(self) -> str:
        return "正在聆听…（看到提示后再说话；说完静音 5 秒自动结束）"

    def _is_asr_hint_active(self) -> bool:
        hint = self.medium_panel._stage_hint.text()
        return hint.startswith("正在聆听") or hint.startswith("仍在录音")

    def _set_asr_stage_hint(self, text: str) -> None:
        self.medium_panel.set_stage_hint(text)

    def _reset_asr_ui(self, *, clear_hint: bool = True) -> None:
        self._asr_listening = False
        self._asr_timeout_timer.stop()
        self._asr_nudge_timer.stop()
        self.medium_panel.set_mic_recording(False)
        if clear_hint and self._is_asr_hint_active():
            self.medium_panel.set_stage_hint("")

    def _on_asr_timeout(self) -> None:
        if not self._asr_listening and not (
            self._c_controller and self._c_controller.asr_is_recording()
        ):
            return
        if self._bc_signals:
            self._bc_signals.asr_stop.emit()
        self._reset_asr_ui(clear_hint=True)
        self.controller.message_added.emit("录音超时，请重试", "system")

    def _on_asr_nudge(self) -> None:
        if self._asr_listening or (
            self._c_controller and self._c_controller.asr_is_recording()
        ):
            self._set_asr_stage_hint("仍在录音，请说话或再次点击结束")

    def _on_mic_clicked(self) -> None:
        if not self._bc_signals:
            return
        voice = self._shared_state.get("voice_settings") or {}
        if not voice.get("asr_enabled", True):
            self.controller.message_added.emit("ASR 已在设置中关闭", "system")
            return
        c_recording = bool(
            self._c_controller and self._c_controller.asr_is_recording()
        )
        if self._asr_listening or c_recording:
            self._reset_asr_ui(clear_hint=False)
            self._bc_signals.asr_stop.emit()
            return
        if not self._c_controller or self._c_load_error:
            self._set_asr_stage_hint("正在加载语音模块…")
            QApplication.processEvents()
            if not self._ensure_c_integration():
                self._reset_asr_ui(clear_hint=True)
                msg = self._c_load_error or "C 端未加载"
                self.controller.message_added.emit(
                    f"语音不可用：{msg}。请确认 client/ 目录存在",
                    "system danger",
                )
                return
        self._asr_listening = True
        self.medium_panel.set_mic_recording(True)
        self._set_asr_stage_hint(self._asr_hint_text())
        self._asr_nudge_timer.start(12000)
        self._asr_timeout_timer.start(65000)
        self._bc_signals.asr_start.emit()

    def _on_asr_session_finished(self, _data) -> None:
        self._reset_asr_ui(clear_hint=True)
        self._request_c_health_check()

    def _on_step_action_finished(self):
        self.medium_panel.set_step_controls_enabled(True)
        if not self._asr_listening and not self._is_asr_hint_active():
            self.medium_panel.set_stage_hint("")

    def _on_status_updated(self, status: str, _label: str):
        busy = status == "processing"
        self.medium_panel.set_input_enabled(not busy)
        self.compact_bar.set_input_enabled(not busy)
        if hasattr(self, "_orange_cat_splash"):
            self._orange_cat_splash.on_status_updated(self._current_ui_theme(), status)

    def _on_task_progress(self, _pct: int, label: str):
        if not self._asr_listening and not self._is_asr_hint_active():
            self.medium_panel.set_stage_hint(label)

    def _wire_native_widgets(self):
        p = self.medium_panel
        b = self.compact_bar
        p.send_clicked.connect(self._on_submit_query)
        b.submit_query.connect(self._on_submit_query)
        p.next_clicked.connect(self.controller.advance_step)
        p.stop_clicked.connect(self.controller.stop_l5_execution)
        b.stop_clicked.connect(self.controller.stop_l5_execution)
        p.compact_requested.connect(self.switch_to_compact)
        p.drag_requested.connect(self.controller.begin_window_drag)
        p.start_services_requested.connect(self._on_start_services)
        p.stop_services_requested.connect(self._on_stop_services)
        p.model_settings_saved.connect(self._on_model_settings_saved)
        p.appearance_settings_saved.connect(self._on_appearance_settings_saved)
        p.voice_settings_saved.connect(self._on_voice_settings_saved)
        p.appearance_preview_requested.connect(self._apply_appearance_preview)
        p.panel_resize_requested.connect(self._on_panel_resize_requested)
        p.panel_restore_size.connect(self._on_panel_restore_size)
        b.expand_requested.connect(self.switch_to_medium)
        b.drag_requested.connect(self.controller.begin_window_drag)
        p.quit_requested.connect(self._quit_application)

    def on_compact_resized(self):
        if self._mode == "compact":
            self._compact_size = [self.width(), self.height()]
            self._state_save_timer().start(500)
        self._apply_window_mask()
        if hasattr(self, "compact_bar"):
            self.compact_bar.update()

    def on_medium_resized(self):
        if (
            hasattr(self, "medium_panel")
            and self.medium_panel.current_panel() != "settings"
        ):
            self._medium_size = [self.width(), self.height()]
            self._state_save_timer().start(500)
        if hasattr(self, "medium_panel"):
            self.medium_panel._update_topbar_chrome()
            self.medium_panel._update_mode_pills_visibility()

    def topbar_min_width(self, *, include_panel_sub: bool = False) -> int:
        if hasattr(self, "medium_panel"):
            return self.medium_panel.topbar_min_width(
                include_panel_sub=include_panel_sub
            )
        from ui.native.layout_tokens import MEDIUM_MIN_W
        return MEDIUM_MIN_W

    def _stop_geometry_anim(self) -> None:
        anim = self._geometry_anim
        if anim is not None:
            anim.stop()
            self._geometry_anim = None

    def _on_geometry_settled(self) -> None:
        self._geometry_anim = None
        self._apply_window_mask()
        if self._mode == "compact" and hasattr(self, "compact_bar"):
            self._compact_size = [self.width(), self.height()]
            self.compact_bar.update()
            self._state_save_timer().start(500)
        elif self._mode == "medium" and hasattr(self, "medium_panel"):
            self._medium_size = [self.width(), self.height()]
            self.medium_panel.update()
            self.on_medium_resized()

    def _on_panel_resize_requested(self, w: int, h: int):
        if (
            not hasattr(self, "medium_panel")
            or self.medium_panel.current_panel() != "settings"
        ):
            return
        if self._size_before_settings is None:
            self._size_before_settings = [self.width(), self.height()]
        self._apply_size_bottom_right(w, h, animated=True)

    def _on_panel_restore_size(self):
        if not self._size_before_settings:
            return
        w, h = self._size_before_settings
        self._size_before_settings = None
        self._apply_size_bottom_right(w, h, animated=True)

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
        target = clamp_geometry_to_screen(
            QRect(g.x(), g.y() - actual, g.width(), new_h)
        )
        self.setGeometry(target)
        self._apply_window_mask()
        self.on_medium_resized()

    def paintEvent(self, event):
        super().paintEvent(event)
        if hasattr(self, "_resize_handler") and USE_NATIVE_UI:
            from PyQt5.QtGui import QPainter
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            self._resize_handler.paint_resize_guides(p)
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
        geo = self.geometry()
        new_x = geo.x() + geo.width() - w
        new_y = geo.y() + geo.height() - h
        target = clamp_geometry_to_screen(QRect(new_x, new_y, w, h))
        if not animated:
            self._stop_geometry_anim()
            self.setGeometry(target)
            self._on_geometry_settled()
            return
        self._stop_geometry_anim()
        self._geometry_anim = resize_keep_bottom_right(
            self,
            target.width(),
            target.height(),
            self,
            animated=True,
            on_finished=self._on_geometry_settled,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_window_mask()

    def moveEvent(self, event):
        super().moveEvent(event)
        if not USE_NATIVE_UI or FRAMED_WINDOW:
            return
        clamped = clamp_geometry_to_screen(self.geometry())
        if clamped.topLeft() != self.geometry().topLeft():
            self.move(clamped.topLeft())

    def _check_api_on_startup(self):
        if not hasattr(self, "controller"):
            return
        for hint in self._startup_hints:
            self.controller.message_added.emit(hint, "system")
        self._last_backend_status_key = ""
        self._backend_connected = False
        QTimer.singleShot(STARTUP_HEALTH_DELAY_MS, self._trigger_backend_health_poll)

    def _trigger_backend_health_poll(self):
        if self.backend_health_worker.isRunning():
            self._schedule_backend_health_poll()
            return
        self.backend_health_worker.start()

    def _schedule_backend_health_poll(self):
        interval = (
            BACKEND_POLL_CONNECTED_MS
            if self._backend_connected
            else BACKEND_POLL_DISCONNECTED_MS
        )
        self._backend_poll_timer.start(interval)

    def _on_backend_health_ready(self, text: str, msg_type: str, connected: bool):
        if not hasattr(self, "controller"):
            return
        is_error = "danger" in msg_type
        if hasattr(self, "medium_panel"):
            self.medium_panel.set_service_status(text)
            self.medium_panel.set_connection_error(is_error, text if is_error else "")

        prev_connected = self._backend_connected
        self._backend_connected = connected
        status_key = f"{connected}|{text}"

        if status_key != self._last_backend_status_key:
            self._last_backend_status_key = status_key
            if not prev_connected and connected:
                self.controller.message_added.emit(
                    "后端已连接，可以开始任务。",
                    "system",
                )
            elif not connected:
                chat_type = msg_type if is_error else "system danger"
                self.controller.message_added.emit(text, chat_type)
            elif connected and prev_connected:
                self.controller.message_added.emit(text, msg_type)

    def _on_submit_query(self, text: str):
        self.controller.submit_query(text)

    def _on_l5_compact_status(self, text: str, active: bool) -> None:
        if hasattr(self, "compact_bar"):
            self.compact_bar.set_l5_status(text, active)

    def _refresh_api_status(self):
        text, msg_type = get_api_status_message()
        if hasattr(self, "medium_panel"):
            self.medium_panel.set_service_status(text)
            is_error = "danger" in msg_type
            self.medium_panel.set_connection_error(is_error, text if is_error else "")
        return text, msg_type

    def _appearance_save_detail(self, merged: dict) -> str:
        ui_theme = merged.get("ui_theme", "current")
        theme_label = appearance_scheme_label(merged)
        font_size = merged.get("font_size", 13)
        if is_luxury_theme(ui_theme):
            bg_label = LUXURY_BG_MODES.get(
                merged.get("luxury_bg_mode", "frosted"), "磨砂黑"
            )
            star = merged.get("luxury_star_intensity", 0)
            font_id = merged.get("luxury_script_font_id", "mrs_delafield")
            sig_label = script_font_labels().get(font_id, font_id)
            return (
                f"{theme_label} · {bg_label} · "
                f"星空 {star} · {sig_label} · 字号 {font_size}px"
            )
        if is_orange_cat_theme(ui_theme):
            return f"{theme_label} · 清新近白 · 字号 {font_size}px"
        shell_label = SHELL_STYLES.get(merged.get("shell_style", "qss"), "QSS 实底")
        art_label = TITLE_ART_MODES.get(
            merged.get("title_art_mode", "gradient"), "渐变艺术字"
        )
        return f"{shell_label} · {theme_label} · {art_label} · 字号 {font_size}px"

    def _on_model_settings_saved(self, data: dict):
        try:
            merged = save_settings_fragment(data)
            apply_user_settings(merged)
            l5_path = sync_l5_sidecar_env(merged)
            restart_note = ""
            if l5_path is not None:
                restart_l5_sidecar()
                restart_note = "；L5 Sidecar (server_A) 已重启以加载新配置"
            self.medium_panel.on_model_settings_applied(
                merged,
                f"模型配置已保存（L5 Sidecar）{restart_note}",
            )
            self._refresh_api_status()
            self.controller.message_added.emit("模型配置已保存并应用", "system")
        except Exception as exc:
            self.medium_panel.on_model_settings_applied(
                data,
                f"保存失败: {exc}",
            )
            self.controller.message_added.emit(f"保存模型设置失败: {exc}", "system danger")

    def _on_appearance_settings_saved(self, data: dict):
        try:
            merged = save_settings_fragment(data)
            self._apply_native_appearance(merged)
            detail = self._appearance_save_detail(merged)
            self.medium_panel.on_appearance_settings_applied(
                merged,
                f"主题外观已保存：{detail}",
            )
            self.controller.message_added.emit("主题外观已保存并应用", "system")
        except Exception as exc:
            self.medium_panel.on_appearance_settings_applied(
                data,
                f"保存失败: {exc}",
            )
            self.controller.message_added.emit(f"保存主题外观失败: {exc}", "system danger")

    def _on_voice_settings_saved(self, data: dict) -> None:
        try:
            merged = save_settings_fragment(data)
            voice = merged.get("voice") or load_voice_settings()
            self._shared_state["voice_settings"] = voice
            self.controller.set_voice_settings(voice)
            if self._c_controller:
                self._c_controller.apply_voice_settings(voice)
            engine = voice.get("asr_engine", "vosk")
            self.medium_panel.on_voice_settings_applied(
                merged,
                f"语音设置已保存并应用（ASR 引擎：{engine}）",
            )
            self.controller.message_added.emit("语音设置已保存并应用", "system")
            self._request_c_health_check()
        except Exception as exc:
            self.medium_panel.on_voice_settings_applied(data, f"保存失败: {exc}")
            self.controller.message_added.emit(f"保存语音设置失败: {exc}", "system danger")

    def _on_start_services(self):
        try:
            settings = load_user_settings()
            sync_l5_sidecar_env(settings)
            restart_l5_sidecar()
            self.medium_panel.set_service_status(
                "已重启 L5 Sidecar（:8011），等待初始化完成后可直接下达指令。"
            )
            self.controller.message_added.emit(
                "已重启 L5 Sidecar", "system"
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
        for name in ("execute_worker",):
            w = getattr(self, name, None)
            if w and w.isRunning():
                w.stop_sse()
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
        if hasattr(self, "tray"):
            self.tray.hide()
        QApplication.quit()

    def switch_to_medium(self, animated: bool = True):
        if self._mode == "medium":
            self.medium_panel.focus_input()
            return
        if self._mode_switching:
            return

        self._dismiss_drawer_overlay()

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
            self._apply_window_mask()
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

        self._dismiss_drawer_overlay()

        outgoing = self.medium_panel
        incoming = self.compact_bar
        w, h = self._compact_size[0], COMPACT_HEIGHT
        self._mode = "compact"
        self._resize_handler.set_enabled(True)

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
            self._apply_window_mask()
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
        tray_icon = svg_icon("logo", 32, "#5a9ec4")
        if not tray_icon.isNull():
            self.tray.setIcon(tray_icon)
            self.setWindowIcon(tray_icon)
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

    def _position_bottom_right(self, margin=60):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        area = screen.availableGeometry()
        geo = clamp_geometry_to_screen(
            QRect(
                area.right() - self.width() - margin,
                area.bottom() - self.height() - margin,
                self.width(),
                self.height(),
            )
        )
        self.move(geo.topLeft())

    def closeEvent(self, event):
        self._save_window_state()
        self._shutdown_c_integration()
        self._shutdown_workers()
        self._stop_backend_if_enabled()
        if hasattr(self, "tray"):
            self.tray.hide()
        event.accept()
