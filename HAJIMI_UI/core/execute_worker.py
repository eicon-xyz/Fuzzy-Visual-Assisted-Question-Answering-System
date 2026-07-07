"""L5 自动执行 worker：POST /execute + SSE /stream/{task_id}。"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PyQt5.QtCore import QThread, pyqtSignal

from config import USE_MOCK_ONLY
from core.api_client import ApiError, cancel_task as api_cancel_task, execute_task as api_execute_task
from core.routing_config import is_l5_route


class ExecuteWorkerThread(QThread):
    sig_execute_success = pyqtSignal(dict, str)
    sig_execute_error = pyqtSignal(str)
    sig_sse_event = pyqtSignal(str, dict)
    sig_progress = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""
        self._task_id: str | None = None
        self._running_sse = True

    @property
    def task_id(self) -> str | None:
        return self._task_id

    def request_execute(self, query: str) -> bool:
        if self.isRunning():
            return False
        self.query = query
        self._task_id = None
        self._running_sse = True
        self.start()
        return True

    def request_cancel(self) -> bool:
        if not self._task_id:
            return False
        try:
            api_cancel_task(self._task_id)
            return True
        except Exception:
            return False

    def stop_sse(self) -> None:
        self._running_sse = False

    def run(self) -> None:
        if USE_MOCK_ONLY or not is_l5_route():
            self.sig_execute_error.emit("Mock 模式不支持 L5 自动执行，请切换指引路由")
            return

        try:
            self.sig_progress.emit(15, "L5 规划与提交执行…")
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(api_execute_task, self.query, None)
                waited = 0
                while not future.done():
                    if waited >= 8:
                        self.sig_progress.emit(45, "Planning Agent 分解步骤…")
                    time.sleep(1)
                    waited += 1
                result = future.result()

            self._task_id = result.get("task_id")
            if not self._task_id:
                self.sig_execute_error.emit("A 端未返回 task_id")
                return

            self.sig_progress.emit(60, "L5 自动执行中…")
            self.sig_execute_success.emit(result, "")
            self._consume_sse(self._task_id)
        except ApiError as exc:
            self.sig_execute_error.emit(str(exc))
        except Exception as exc:
            self.sig_execute_error.emit(str(exc))

    def _consume_sse(self, task_id: str) -> None:
        from config import API_BASE_URL

        url = f"{API_BASE_URL.rstrip('/')}/api/demo/stream/{task_id}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=360) as resp:
                event_type = ""
                for raw_line in resp:
                    if not self._running_sse:
                        break
                    try:
                        line = raw_line.decode("utf-8").strip()
                    except Exception:
                        continue
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:") and event_type:
                        payload = line[5:].strip()
                        if not payload:
                            continue
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if event_type != "heartbeat":
                            self.sig_sse_event.emit(event_type, data)
                        if event_type in (
                            "task_done",
                            "task_failed",
                            "task_cancelled",
                        ):
                            break
        except urllib.error.URLError:
            pass
        except Exception:
            pass
