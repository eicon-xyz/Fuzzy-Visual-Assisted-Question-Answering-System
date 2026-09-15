import time
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from core.bc_signals import AuditRecordBuilder


class AppController(QObject):
    """原生 UI 业务控制器 — 仅 L5 自动执行模式。

    L4 指引链路（process/step/inspect/relocate/prepare/overlay 标注）已整体移除；
    执行链 = ExecuteWorkerThread → Sidecar :8011 /execute + SSE /stream。
    """

    message_added = pyqtSignal(str, str)
    steps_updated = pyqtSignal(list, int)
    status_updated = pyqtSignal(str, str)
    l5_compact_status_updated = pyqtSignal(str, bool)
    mode_compact_requested = pyqtSignal()

    def __init__(
        self,
        execute_worker=None,
        main_window=None,
        bc_signals=None,
        voice_settings: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(main_window)
        self._main_window = main_window
        self.execute_worker = execute_worker
        self._bc_signals = bc_signals
        self._voice_settings = dict(voice_settings or {})
        self.task_id = None
        self.steps = []
        self.current_step_index = 0
        self._l5_mode = False
        self._l5_blocked_pending = False
        self._task_query = ""
        self._task_started_at: Optional[float] = None
        self._audit_emitted = False
        self._l5_overlay_hint_shown = False

        if self.execute_worker:
            self.execute_worker.sig_execute_success.connect(self.on_execute_success)
            self.execute_worker.sig_execute_error.connect(self.on_execute_error)
            self.execute_worker.sig_sse_event.connect(self.on_l5_sse_event)
            self.execute_worker.sig_progress.connect(self._on_execute_progress)

    def _medium_panel(self):
        win = self._main_window
        if win and hasattr(win, "medium_panel"):
            return win.medium_panel
        return None

    def _on_execute_progress(self, _pct: int, label: str) -> None:
        panel = self._medium_panel()
        if panel:
            panel.set_stage_hint(label)

    def resize_window(self, width: int, height: int):
        win = self._main_window
        if not win:
            return
        width = max(280, int(width))
        height = max(52, int(height))
        geo = win.geometry()
        win.resize(width, height)
        win.move(geo.x() + geo.width() - width, geo.y() + geo.height() - height)

    def begin_window_drag(self):
        win = self._main_window
        if not win:
            return
        handle = win.windowHandle()
        if handle and hasattr(handle, "startSystemMove"):
            handle.startSystemMove()

    def set_voice_settings(self, voice_settings: Dict[str, Any]) -> None:
        self._voice_settings = dict(voice_settings or {})

    # ── 任务提交：一律 L5 自动执行 ──────────────────────────────

    def submit_query(self, text: str):
        print(f"[Controller] 收到用户指令: {text}")
        self.message_added.emit(text, "user")
        self.status_updated.emit("processing", "AI 思考中...")
        self.task_id = None
        self.steps = []
        self.current_step_index = 0
        self._task_query = text.strip()
        self._task_started_at = None
        self._audit_emitted = False
        self._l5_mode = False
        self._l5_blocked_pending = False
        self._l5_overlay_hint_shown = False

        panel = self._medium_panel()
        if panel and panel.is_l5_completed:
            panel.finish_l5_execution()

        if panel and not panel.ensure_l5_consent(self._main_window):
            self.message_added.emit("已取消 L5 自动执行", "system")
            self.status_updated.emit("idle", "准备就绪")
            return

        if self.execute_worker and self.execute_worker.isRunning():
            self.message_added.emit("已取消上一 L5 任务，开始新任务", "system")
            self.execute_worker.request_cancel()
            self.execute_worker.stop_sse()
            self.execute_worker.wait(5000)

        self._l5_mode = True
        if panel:
            panel.begin_l5_planning()
            panel.notify_l5_audit_compat("")
        self.message_added.emit(
            "L5 自动执行已启动；审计 route 将按 L3 上报（契约兼容）。",
            "system",
        )
        if not self.execute_worker:
            self.message_added.emit("错误：L5 执行线程未初始化", "system danger")
            self.status_updated.emit("idle", "准备就绪")
            self._l5_mode = False
            return
        if not self.execute_worker.request_execute(text):
            self.message_added.emit("请等待当前任务完成", "system")
            self.status_updated.emit("processing", "处理中...")

    def stop_l5_execution(self) -> None:
        if not self._l5_mode:
            return
        if self.execute_worker:
            self.execute_worker.request_cancel()
            self.execute_worker.stop_sse()
        self._emit_audit("cancel")
        self.message_added.emit("已请求停止 L5 自动执行", "system")
        self.status_updated.emit("idle", "准备就绪")
        self._reset_l5_state()

    def advance_step(self):
        """面板「下一步」按钮在 L5 下 = 批准高风险阻塞步骤。"""
        panel = self._medium_panel()
        if panel and panel.is_l5_completed:
            panel.finish_l5_execution()
            return
        if self._l5_blocked_pending:
            self._l5_blocked_pending = False
            self.message_added.emit("已批准继续", "system")

    def _complete_l5_state(self, outcome: str = "done") -> None:
        self._l5_mode = False
        self._l5_blocked_pending = False
        self.l5_compact_status_updated.emit("", False)
        panel = self._medium_panel()
        if panel:
            panel.complete_l5_execution(outcome=outcome)
            if self.steps:
                panel.mirror_l5_steps_to_guide(self.steps)

    def _reset_l5_state(self) -> None:
        self._l5_mode = False
        self._l5_blocked_pending = False
        self.l5_compact_status_updated.emit("", False)
        panel = self._medium_panel()
        if panel:
            panel.finish_l5_execution()

    def _update_l5_compact_status(self) -> None:
        panel = self._medium_panel()
        if not panel or not self._l5_mode:
            self.l5_compact_status_updated.emit("", False)
            return
        self.l5_compact_status_updated.emit(panel.l5_progress_label(), True)

    def _maybe_l5_desktop_overlay(self, summary: str) -> None:
        """Phase 1 占位：桌面标注需 Sidecar 回传 bbox 后启用。"""
        from core.user_settings import load_user_settings

        if not load_user_settings().get("l5_desktop_overlay", True):
            return
        if not summary or "click" not in summary.lower():
            return
        if not self._l5_overlay_hint_shown:
            self._l5_overlay_hint_shown = True
            self.message_added.emit(
                "桌面标注待 Sidecar 回传坐标；时间线内可查看执行详情",
                "system",
            )
        # Reserved: map bbox from future tool_result payload

    def handle_l5_hotkey(self, key: str) -> bool:
        from core.user_settings import load_user_settings

        if not self._l5_mode:
            return False
        settings = load_user_settings()
        approve = (settings.get("shortcut_l5_approve") or "H").upper()
        stop = (settings.get("shortcut_l5_stop") or "J").upper()
        if key.upper() == stop:
            self.stop_l5_execution()
            return True
        if key.upper() == approve and self._l5_blocked_pending:
            self._l5_blocked_pending = False
            self.message_added.emit("已批准继续高风险步骤", "system")
            return True
        return False

    # ── L5 结果/SSE 处理 ────────────────────────────────────────

    def on_execute_success(self, response: dict, _fingerprint: str) -> None:
        self.task_id = response.get("task_id")
        self._task_started_at = time.time()
        plan = response.get("plan") or {}
        raw_steps = plan.get("steps") or []
        self.steps = [
            {
                "step_index": s.get("step_index", i + 1),
                "description": s.get("instruction", ""),
                "instruction": s.get("instruction", ""),
                "status": "pending",
            }
            for i, s in enumerate(raw_steps)
        ]
        self.current_step_index = 0
        panel = self._medium_panel()
        if panel:
            panel.notify_l5_audit_compat("")
        self.steps_updated.emit(self.steps, 0)
        if panel:
            shot = response.get("screenshot_base64") or ""
            if shot:
                panel.show_l5_initial_screenshot(0, shot)
        self.status_updated.emit("executing", "L5 自动执行中")
        self._update_l5_compact_status()

    def _maybe_l5_llm_auth_hint(self, message: str) -> None:
        text = (message or "").lower()
        if "401" not in text and "llm error" not in text:
            return
        self.message_added.emit(
            "8011 Sidecar 的 LLM Key 无效或未同步。"
            "请在设置中保存模型配置（写入 server_A/server/.env），或重启 L5 Sidecar。",
            "system",
        )

    def on_execute_error(self, error_msg: str) -> None:
        self._emit_audit("fail")
        self.message_added.emit(f"L5 执行失败: {error_msg}", "system danger")
        if "无法直接操控您的电脑" in error_msg:
            print(
                f"[L5] physical redline after normalize; "
                f"query={self._task_query!r}"
            )
            self.message_added.emit(
                "提示：该句式可能未被 L5 归一化覆盖，可暂用「打开 XXX」或「怎么 XXX」重试。",
                "system",
            )
        self._maybe_l5_llm_auth_hint(error_msg)
        self.status_updated.emit("idle", "准备就绪")
        self._complete_l5_state("error")

    def on_l5_sse_event(self, event_type: str, data: dict) -> None:
        panel = self._medium_panel()
        if panel:
            panel.handle_l5_sse(event_type, data)
        if event_type == "step_start":
            idx = int(data.get("step_index", 1)) - 1
            self.current_step_index = max(0, idx)
            self.steps_updated.emit(self.steps, self.current_step_index)
        elif event_type == "step_done":
            idx = int(data.get("step_index", 1)) - 1
            summary = data.get("action_summary") or ""
            self._maybe_l5_desktop_overlay(summary)
            if idx < len(self.steps):
                desc = self.steps[idx].get("description") or summary
                self._maybe_enqueue_tts(desc, priority=1)
        elif event_type == "step_blocked":
            self._l5_blocked_pending = True
            self.message_added.emit(
                data.get("message")
                or "检测到高风险步骤，按 H 批准继续或 J 停止",
                "system danger",
            )
        elif event_type == "step_failed":
            summary = str(
                data.get("action_summary")
                or data.get("reason")
                or data.get("error")
                or ""
            )
            self._maybe_l5_llm_auth_hint(summary)
        elif event_type == "task_done":
            self.current_step_index = len(self.steps)
            self._emit_audit("success")
            self.message_added.emit(
                "L5 执行完成，审计 route=L3（契约兼容）",
                "system",
            )
            self.status_updated.emit("idle", "准备就绪")
            self._complete_l5_state("done")
        elif event_type == "task_failed":
            self._emit_audit("fail")
            fail_msg = str(data.get("message") or data.get("reason") or "")
            self.message_added.emit("L5 执行失败", "system danger")
            self._maybe_l5_llm_auth_hint(fail_msg)
            self.status_updated.emit("idle", "准备就绪")
            self._complete_l5_state("failed")
        elif event_type == "task_cancelled":
            if self._l5_mode:
                self._emit_audit("cancel")
                self.message_added.emit("L5 已取消", "system danger")
                self.status_updated.emit("idle", "准备就绪")
                self._complete_l5_state("cancelled")
        self._update_l5_compact_status()

    # ── 语音 / 审计 ─────────────────────────────────────────────

    def _maybe_enqueue_tts(self, text: str, priority: int = 0) -> None:
        if not self._bc_signals or not text:
            return
        if not self._voice_settings.get("tts_enabled", True):
            return
        try:
            self._bc_signals.tts_enqueue.emit(text, priority, False)
        except Exception:
            pass

    def _emit_audit(self, result: str) -> None:
        if self._audit_emitted or not self._bc_signals:
            return
        if not self.task_id and not self._task_query:
            return
        record = AuditRecordBuilder.build(
            task_id=self.task_id,
            query=self._task_query,
            intent=None,
            route="L3",  # 审计契约兼容：L5 按 L3 上报
            steps=self.steps,
            completed_steps=self.current_step_index,
            result=result,
            started_at=self._task_started_at,
            redline_triggered=result == "rejected",
        )
        try:
            self._bc_signals.audit_submit.emit(record)
            self._audit_emitted = True
        except Exception:
            pass

    def on_asr_result(self, data) -> None:
        if isinstance(data, dict):
            transcript = (data.get("transcript") or "").strip()
            confidence = float(data.get("confidence") or 0.0)
            error = data.get("error")
        else:
            transcript = str(data or "").strip()
            confidence = 1.0
            error = None

        if error:
            self.message_added.emit(f"语音识别失败：{error}", "system danger")
            return
        if not transcript:
            self.message_added.emit("未识别到语音内容", "system")
            return

        low_confidence = confidence < 0.6
        if self._main_window and hasattr(self._main_window, "medium_panel"):
            panel = self._main_window.medium_panel
            if hasattr(panel, "set_input_from_asr"):
                panel.set_input_from_asr(transcript, low_confidence=low_confidence)
        if low_confidence:
            self.message_added.emit("识别置信度较低，请确认后发送", "system")
