# ui/bridge_web.py — WebEngine 回退路径用的 JS 桥接
import json
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from core.annotation_mapper import to_overlay_items
from core.api_client import advance_step as api_advance_step
from core.coordinate_mapper import REF_H, REF_W
from core.mock_backend import register_task
from core.screen_utils import capture_screen, compute_fingerprint


class Bridge(QObject):
    """Python 端桥接对象，暴露给 JavaScript 的 pyBridge（WebEngine 回退路径）"""

    sig_add_message = pyqtSignal(str, str)
    sig_update_steps = pyqtSignal(list, int)
    sig_update_status = pyqtSignal(str, str)
    sig_update_overlay = pyqtSignal(list)
    sig_clear_overlay = pyqtSignal()
    sig_render_blueprint = pyqtSignal(list, int)
    sig_show_suspension = pyqtSignal(str)
    sig_hide_suspension = pyqtSignal()

    def __init__(self, worker=None, main_window=None):
        super().__init__(main_window)
        self._main_window = main_window
        self.worker = worker
        self.task_id = None
        self.fingerprint = None
        self.steps = []
        self.current_step_index = 0
        self._screen_size = (REF_W, REF_H)
        self._ref_size = (REF_W, REF_H)

        if self.worker:
            self.worker.sig_process_success.connect(self.on_process_success)
            self.worker.sig_process_error.connect(self.on_process_error)
            self.worker.sig_redline_triggered.connect(self.on_redline)

    @pyqtSlot(int, int)
    def resizeWindow(self, width, height):
        win = self._main_window
        if not win:
            return
        width = max(280, int(width))
        height = max(52, int(height))
        geo = win.geometry()
        win.resize(width, height)
        win.move(geo.x() + geo.width() - width, geo.y() + geo.height() - height)

    @pyqtSlot()
    def beginWindowDrag(self):
        win = self._main_window
        if not win:
            return
        handle = win.windowHandle()
        if handle and hasattr(handle, "startSystemMove"):
            handle.startSystemMove()

    @pyqtSlot(str)
    def sendUserInput(self, text):
        print(f"[Bridge] 收到用户指令: {text}")
        self.sig_add_message.emit(text, "user")
        self.sig_update_status.emit("processing", "AI 思考中...")
        self.sig_clear_overlay.emit()
        self.task_id = None
        self.steps = []
        self.current_step_index = 0

        if self.worker:
            if not self.worker.request_process(text):
                self.sig_add_message.emit("请等待当前任务完成", "system")
                self.sig_update_status.emit("processing", "处理中...")
        else:
            self.sig_add_message.emit("错误：任务线程未初始化", "system danger")
            self.sig_update_status.emit("idle", "准备就绪")

    @pyqtSlot()
    def requestStepAdvance(self):
        print("[Bridge] requestStepAdvance 被调用")
        self._request_step_action("advance")

    @pyqtSlot()
    def onNextStep(self):
        self.requestStepAdvance()

    @pyqtSlot()
    def onPrevStep(self):
        if not self.task_id or not self.steps:
            self.sig_add_message.emit("暂无步骤可回退", "system danger")
            return
        self._request_step_action("rollback")

    @pyqtSlot(str)
    def onSuspensionResolve(self, action):
        print(f"[Bridge] 挂起处理: {action}")
        self.sig_hide_suspension.emit()
        if action == "skip":
            self._request_step_action("skip")
        elif action == "rollback":
            self._request_step_action("rollback")
        elif action == "abort":
            self._request_step_action("terminate")

    @pyqtSlot(str)
    def onPanelSwitch(self, panel):
        print(f"[Bridge] 面板切换: {panel}")

    def onTargetAreaClicked(self):
        print("[Bridge] 红框区域被点击")
        if not self.task_id or not self.steps:
            self.sig_add_message.emit("请先等待任务生成步骤后再推进", "system danger")
            return
        if self.current_step_index >= len(self.steps):
            self.sig_add_message.emit("已是最后一步", "system")
            return
        self.requestStepAdvance()

    def _refresh_fingerprint(self):
        screenshot = capture_screen()
        if screenshot is not None:
            self.fingerprint = compute_fingerprint(screenshot)

    def _request_step_action(self, action: str):
        if not self.task_id or not self.steps:
            self.sig_add_message.emit("请先等待任务生成步骤后再推进", "system danger")
            return

        self._refresh_fingerprint()
        step_index = self.current_step_index + 1

        try:
            response = api_advance_step(
                self.task_id,
                step_index,
                self.fingerprint or "",
                action,
                self.steps,
            )
        except Exception as exc:
            self.sig_add_message.emit(f"步骤推进失败: {exc}", "system danger")
            return

        self._handle_step_response(response)

    def _handle_step_response(self, response: dict):
        action = response.get("action", "")
        message = response.get("message") or ""

        if action == "suspended":
            self.sig_show_suspension.emit(
                message or "检测到屏幕状态与预期不符，您要跳过此步还是回退重试？"
            )
            self.sig_update_status.emit("suspended", "异常挂起")
            return

        if action == "terminated":
            self.sig_add_message.emit("任务已终止。", "system danger")
            self.sig_update_status.emit("idle", "已终止")
            self.sig_clear_overlay.emit()
            return

        if action == "rollback":
            new_step = response.get("current_step", max(1, self.current_step_index))
            self.current_step_index = max(0, int(new_step) - 1)
            self._sync_frontend()
            self.sig_add_message.emit(f"已回退到第 {self.current_step_index + 1} 步", "system")
            self.sig_update_status.emit("executing", "正在指引中")
            return

        if action in ("advance", "skip"):
            prev_index = self.current_step_index
            new_step = response.get("current_step")
            if new_step is not None:
                self.current_step_index = max(0, int(new_step) - 1)
            else:
                self.current_step_index += 1

            next_step = response.get("next_step")
            if next_step and 0 <= self.current_step_index < len(self.steps):
                self.steps[self.current_step_index] = next_step

            if prev_index < len(self.steps):
                self.sig_add_message.emit(
                    f"第 {prev_index + 1} 步已结束",
                    "system",
                )

            if self.current_step_index < len(self.steps):
                desc = (
                    self.steps[self.current_step_index].get("description")
                    or self.steps[self.current_step_index].get("action", "")
                )
                self._sync_frontend()
                self.sig_add_message.emit(
                    f"第 {self.current_step_index + 1} 步: {desc}",
                    "system",
                )
                self.sig_update_status.emit("executing", "正在指引中")
            else:
                self._finish_task()
            return

        if action == "complete":
            self._finish_task()
            return

        self.sig_add_message.emit(f"未知步骤响应: {action}", "system danger")

    def _finish_task(self):
        if self.steps:
            frontend = self._frontend_steps()
            done_index = len(self.steps)
            self.sig_update_steps.emit(frontend, done_index)
            self.sig_render_blueprint.emit(frontend, done_index)
        self.sig_add_message.emit("任务已结束", "system")
        self.sig_update_status.emit("idle", "已结束")
        self.sig_clear_overlay.emit()

    def on_process_success(self, response, fingerprint):
        self.task_id = response.get("task_id")
        self.fingerprint = fingerprint
        self.steps = response.get("steps") or []
        self.current_step_index = 0

        size = response.get("_screen_size") or [REF_W, REF_H]
        self._screen_size = (int(size[0]), int(size[1]))
        if response.get("_mock"):
            self._ref_size = self._screen_size
        else:
            ref = response.get("_ref_size") or [REF_W, REF_H]
            self._ref_size = (int(ref[0]), int(ref[1]))

        if self.task_id and self.steps and response.get("_mock"):
            register_task(self.task_id, self.steps)

        intent = response.get("intent") or {}
        summary = intent.get("summary", "操作指引")
        if response.get("_mock"):
            source_tag = " [Mock]"
        elif response.get("_source") == "server":
            source_tag = " [Server]"
        else:
            source_tag = ""
        self.sig_add_message.emit(
            f"已理解意图「{summary}」，共 {len(self.steps)} 步{source_tag}",
            "system",
        )

        self._sync_frontend()
        self.sig_update_status.emit("executing", "正在指引中")
        self.sig_render_blueprint.emit(self._frontend_steps(), 0)

    def on_process_error(self, error_msg):
        self.sig_add_message.emit(f"处理失败: {error_msg}", "system danger")
        self.sig_update_status.emit("idle", "准备就绪")
        self.sig_clear_overlay.emit()

    def on_redline(self, msg):
        self.sig_add_message.emit(msg, "system danger")
        self.sig_update_status.emit("idle", "已拦截")
        self.sig_clear_overlay.emit()

    def _frontend_steps(self):
        return [
            {
                "desc": s.get("description") or s.get("action", ""),
                "action": s.get("action", ""),
                "annotation": s.get("annotation"),
            }
            for s in self.steps
        ]

    def _sync_frontend(self):
        frontend = self._frontend_steps()
        idx = min(self.current_step_index, max(0, len(self.steps) - 1))
        self.sig_update_steps.emit(frontend, idx)
        self.sig_render_blueprint.emit(frontend, idx)
        if self.steps and 0 <= self.current_step_index < len(self.steps):
            step = self.steps[self.current_step_index]
            items = to_overlay_items(
                step.get("annotation"),
                self.current_step_index + 1,
                screen_size=self._screen_size,
                ref_size=self._ref_size,
            )
            self.sig_update_overlay.emit(items)
