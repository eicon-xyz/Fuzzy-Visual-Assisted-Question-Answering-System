"""
HAJIMI 自动操作助手 — 任务监控面板

Windows 标准窗口风格，浅色灰白主题。
布局: 输入栏 + 步骤列表 + 截图/日志分栏 + 控制按钮
"""
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QPixmap, QColor, QPalette
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QPlainTextEdit,
    QSplitter, QFrame, QSizePolicy, QSpacerItem,
)

# ═══════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════

STATUS_ICONS = {
    "pending": "⏳",
    "active": "🔄",
    "done": "✅",
    "failed": "❌",
    "blocked": "🚫",
    "skipped": "⏭️",
}

STYLE = """
AgentPanel {
    background: #f0f2f5;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 12px;
}
QLineEdit#query_input {
    border: 1px solid #d0d5dd;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    background: #ffffff;
}
QLineEdit#query_input:focus {
    border-color: #4a90d9;
}
QPushButton#execute_btn {
    background: #4a90d9;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton#execute_btn:hover {
    background: #3a7bc8;
}
QPushButton#execute_btn:disabled {
    background: #a0c4e8;
}
QLabel#progress_label {
    font-size: 13px;
    font-weight: bold;
    color: #1e293b;
    padding: 6px 0;
}
QListWidget#step_list {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    background: #ffffff;
    padding: 4px;
}
QListWidget#step_list::item {
    padding: 6px 8px;
    border-bottom: 1px solid #f1f5f9;
}
QLabel#screenshot_label {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    background: #f8fafc;
    min-width: 320px;
    min-height: 240px;
    alignment: center;
}
QPlainTextEdit#log_output {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    background: #ffffff;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
    padding: 4px;
}
QPushButton#start_btn  { background: #22c55e; color: white; border: none; border-radius: 4px; padding: 6px 14px; }
QPushButton#start_btn:hover { background: #16a34a; }
QPushButton#pause_btn  { background: #f59e0b; color: white; border: none; border-radius: 4px; padding: 6px 14px; }
QPushButton#pause_btn:hover { background: #d97706; }
QPushButton#resume_btn { background: #3b82f6; color: white; border: none; border-radius: 4px; padding: 6px 14px; }
QPushButton#resume_btn:hover { background: #2563eb; }
QPushButton#stop_btn   { background: #ef4444; color: white; border: none; border-radius: 4px; padding: 6px 14px; font-weight: bold; }
QPushButton#stop_btn:hover { background: #dc2626; }
QPushButton:disabled { background: #94a3b8; color: #e2e8f0; }
"""


# ═══════════════════════════════════════════════════════════════════════════
# SSE 客户端线程（内置在 panel 模块中）
# ═══════════════════════════════════════════════════════════════════════════

class SSEClient(QThread):
    event_received = pyqtSignal(str, dict)  # (event_type, data)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, task_id: str, base_url: str = "http://127.0.0.1:8010"):
        super().__init__()
        self.task_id = task_id
        self.base_url = base_url
        self._running = True

    def run(self):
        import urllib.request
        url = f"{self.base_url}/api/demo/stream/{self.task_id}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=180) as resp:
                self.connected.emit()
                event_type = ""
                data_str = ""
                for line in resp:
                    if not self._running:
                        break
                    try:
                        line_text = line.decode("utf-8").strip()
                    except Exception:
                        continue
                    if line_text.startswith("event:"):
                        event_type = line_text[6:].strip()
                    elif line_text.startswith("data:"):
                        data_str = line_text[5:].strip()
                        if data_str:
                            try:
                                import json
                                data = json.loads(data_str)
                                self.event_received.emit(event_type, data)
                            except Exception:
                                pass
        except Exception as e:
            self.disconnected.emit()
        finally:
            self.disconnected.emit()

    def stop(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════════════════
# 主面板
# ═══════════════════════════════════════════════════════════════════════════

class AgentPanel(QWidget):
    """任务监控面板 — B 端主界面"""

    send_query = pyqtSignal(str)          # 执行指令
    cancel_requested = pyqtSignal(str)     # 取消任务（task_id）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)

        self._task_id = None
        self._sse_client = None
        self._steps_data = []  # [{step_index, status, ...}]
        self._task_status = "idle"  # idle|executing|paused|completed|failed|cancelled

        self._init_ui()
        self._update_button_states()

    # ── UI 构建 ───────────────────────────────────────────────────────────

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # ── 顶部输入栏 ──
        input_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setObjectName("query_input")
        self.query_input.setPlaceholderText("输入你想让AI做的事，例如：帮我把微信装到D盘...")
        self.query_input.returnPressed.connect(self._on_execute)
        input_row.addWidget(self.query_input, 1)

        self.execute_btn = QPushButton("执 行")
        self.execute_btn.setObjectName("execute_btn")
        self.execute_btn.clicked.connect(self._on_execute)
        input_row.addWidget(self.execute_btn)
        root.addLayout(input_row)

        # ── 进度标题 ──
        self.progress_label = QLabel("就绪")
        self.progress_label.setObjectName("progress_label")
        root.addWidget(self.progress_label)

        # ── 步骤列表 ──
        self.step_list = QListWidget()
        self.step_list.setObjectName("step_list")
        self.step_list.setMaximumHeight(180)
        root.addWidget(self.step_list)

        # ── 下部分割区 ──
        splitter = QSplitter(Qt.Horizontal)

        # 截图预览
        self.screenshot_label = QLabel("截图预览")
        self.screenshot_label.setObjectName("screenshot_label")
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setMinimumSize(320, 240)
        splitter.addWidget(self.screenshot_label)

        # 执行日志
        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("log_output")
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("执行日志将显示在此...")
        splitter.addWidget(self.log_output)

        splitter.setSizes([320, 400])
        root.addWidget(splitter, 1)

        # ── 底部控制栏 ──
        ctrl_row = QHBoxLayout()

        self.start_btn = QPushButton("▶ 开始 (Ctrl+1)")
        self.start_btn.setObjectName("start_btn")
        self.start_btn.clicked.connect(self._on_execute)
        ctrl_row.addWidget(self.start_btn)

        self.pause_btn = QPushButton("⏸ 暂停 (Ctrl+2)")
        self.pause_btn.setObjectName("pause_btn")
        self.pause_btn.clicked.connect(self._on_pause)
        ctrl_row.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("▶ 恢复 (Ctrl+3)")
        self.resume_btn.setObjectName("resume_btn")
        self.resume_btn.clicked.connect(self._on_resume)
        ctrl_row.addWidget(self.resume_btn)

        self.stop_btn = QPushButton("⏹ 停止 (Ctrl+4)")
        self.stop_btn.setObjectName("stop_btn")
        self.stop_btn.clicked.connect(self._on_stop)
        ctrl_row.addWidget(self.stop_btn)

        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

    # ── 公开方法 ──────────────────────────────────────────────────────────

    def set_screenshot(self, pixmap: QPixmap):
        """设置截图预览。"""
        scaled = pixmap.scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.screenshot_label.setPixmap(scaled)

    def set_placeholder_screenshot(self, text: str = "截图预览"):
        """设置占位截图。"""
        self.screenshot_label.setText(text)

    def append_log(self, message: str, level: str = "info"):
        """追加日志行。"""
        color = {"info": "#1e293b", "warn": "#d97706", "error": "#ef4444", "debug": "#64748b"}.get(level, "#1e293b")
        self.log_output.appendHtml(f'<span style="color:{color}">{message}</span>')

    def clear(self):
        """清空所有状态。"""
        self._task_id = None
        self._steps_data = []
        self._task_status = "idle"
        self.step_list.clear()
        self.log_output.clear()
        self.progress_label.setText("就绪")
        self.screenshot_label.setText("截图预览")
        self._update_button_states()

    def set_task_status(self, status: str):
        """设置任务状态并更新按钮。"""
        self._task_status = status
        self._update_button_states()

    def update_step(self, step_index: int, status: str, duration_ms: int = 0):
        """更新步骤列表中的某个步骤的状态。"""
        for i in range(self.step_list.count()):
            item = self.step_list.item(i)
            data = item.data(Qt.UserRole)
            if data and data.get("step_index") == step_index:
                data["status"] = status
                if duration_ms:
                    data["duration_ms"] = duration_ms
                icon = STATUS_ICONS.get(status, "⏳")
                desc = data.get("description", "")
                if status == "done" and duration_ms:
                    item.setText(f"{icon}  {desc}    {duration_ms/1000:.1f}s")
                else:
                    item.setText(f"{icon}  {desc}")
                if status == "active":
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                else:
                    font = item.font()
                    font.setBold(False)
                    item.setFont(font)
                return
        self.progress_label.setText(
            f"📋 任务执行中    {self._count_done()}/{self.step_list.count()}"
        )

    def load_plan(self, plan: dict):
        """从 SSE plan_ready 或 execute 响应加载步骤列表。"""
        self.step_list.clear()
        self._steps_data = []
        goal = plan.get("goal", "")
        steps = plan.get("steps", [])
        self.progress_label.setText(f"📋 任务: {goal}    0/{len(steps)}")
        for s in steps:
            si = s.get("step_index", len(self._steps_data) + 1)
            desc = s.get("description", f"步骤 {si}")
            status = s.get("status", "pending")
            icon = STATUS_ICONS.get(status, "⏳")
            item = QListWidgetItem(f"{icon}  {desc}")
            item.setData(Qt.UserRole, {
                "step_index": si,
                "status": status,
                "description": desc,
                "duration_ms": 0,
            })
            self.step_list.addItem(item)
            self._steps_data.append(s)

    def _count_done(self) -> int:
        count = 0
        for i in range(self.step_list.count()):
            data = self.step_list.item(i).data(Qt.UserRole)
            if data and data.get("status") == "done":
                count += 1
        return count

    # ── SSE 事件处理 ──────────────────────────────────────────────────────

    def on_sse_event(self, event_type: str, data: dict):
        """处理 SSE 事件。"""
        if event_type == "heartbeat":
            pass
        elif event_type == "plan_ready":
            self.load_plan(data)
            self.set_task_status("executing")
            self.append_log(f"AI 已规划 {data.get('total_steps', 0)} 个步骤", "info")
        elif event_type == "step_start":
            si = data.get("step_index", 0)
            self.update_step(si, "active")
            desc = data.get("description") or data.get("instruction", "")
            self.append_log(f">>> 步骤 {si}: {desc}", "info")
        elif event_type == "step_executing":
            self.append_log(f"   └ {data.get('detail', '')}", "debug")
        elif event_type == "step_done":
            si = data.get("step_index", 0)
            self.update_step(si, "done", data.get("duration_ms", 0))
            self.append_log(f"   ✅ 步骤 {si} 完成 ({data.get('duration_ms', 0)}ms)", "info")
        elif event_type == "step_failed":
            si = data.get("step_index", 0)
            self.update_step(si, "failed")
            self.append_log(f"   ❌ 步骤 {si} 失败: {data.get('error', '')}", "error")
        elif event_type == "step_retry":
            self.append_log(f"   🔄 重试步骤 {data.get('step_index', '?')}", "warn")
        elif event_type == "step_blocked":
            si = data.get("step_index", 0)
            self.update_step(si, "blocked")
            self.append_log(f"   🚫 步骤 {si} 被拦截: {data.get('reason', '')}", "warn")
        elif event_type == "log":
            self.append_log(data.get("message", ""), data.get("level", "info"))
        elif event_type == "screenshot":
            b64 = data.get("image_base64", "")
            if b64:
                try:
                    import base64
                    img_data = base64.b64decode(b64.split(",", 1)[-1])
                    pix = QPixmap()
                    pix.loadFromData(img_data)
                    if not pix.isNull():
                        self.set_screenshot(pix)
                except Exception:
                    pass
        elif event_type == "task_done":
            self.set_task_status("completed")
            done = data.get("steps_completed", 0)
            fail = data.get("steps_failed", 0)
            total = data.get("total_steps", 0)
            self.progress_label.setText(f"📋 任务完成    {done}/{total} (失败 {fail})")
            self.append_log(f"任务{'成功' if data.get('success') else '部分失败'} ({done}/{total})", "info")
        elif event_type == "task_error":
            self.set_task_status("failed")
            self.append_log(f"💥 任务错误: {data.get('error', '')}", "error")

    def _connect_sse(self, task_id: str):
        """连接 SSE 事件流。"""
        if self._sse_client:
            self._sse_client.stop()
            self._sse_client.wait(1000)
        self._sse_client = SSEClient(task_id)
        self._sse_client.event_received.connect(self.on_sse_event)
        self._sse_client.disconnected.connect(lambda: self.set_task_status("idle"))
        self._sse_client.start()

    # ── 按钮事件 ──────────────────────────────────────────────────────────

    def _on_execute(self):
        query = self.query_input.text().strip()
        if not query:
            return
        self.clear()
        self.set_task_status("executing")
        self.append_log(f"用户指令: {query}", "info")
        self.send_query.emit(query)

    def _on_pause(self):
        if self._task_id:
            self.cancel_requested.emit(self._task_id)
        self.set_task_status("paused")
        self.append_log("⏸ 已暂停", "warn")

    def _on_resume(self):
        # MVP: 暂不支持恢复，需重新执行
        self.set_task_status("executing")
        self.append_log("▶ 恢复执行（重新提交）", "info")
        self._on_execute()

    def _on_stop(self):
        if self._task_id:
            self.cancel_requested.emit(self._task_id)
        if self._sse_client:
            self._sse_client.stop()
        self.set_task_status("cancelled")
        self.append_log("⏹ 已停止", "warn")

    # ── 按钮状态机 ────────────────────────────────────────────────────────

    def _update_button_states(self):
        s = self._task_status
        idle = s in ("idle", "completed", "failed", "cancelled")
        self.start_btn.setEnabled(idle)
        self.pause_btn.setEnabled(s == "executing")
        self.resume_btn.setEnabled(s == "paused")
        self.stop_btn.setEnabled(s in ("executing", "paused"))
        self.execute_btn.setEnabled(idle)
        self.query_input.setEnabled(idle)

    # ── 键盘快捷键 ────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            key = event.key()
            if key == Qt.Key_1:
                self._on_execute()
            elif key == Qt.Key_2:
                self._on_pause()
            elif key == Qt.Key_3:
                self._on_resume()
            elif key == Qt.Key_4:
                self._on_stop()
        super().keyPressEvent(event)
