from PyQt5.QtCore import QThread, pyqtSignal

from core.api_client import ApiError, process as api_process
from core.screen_utils import capture_screen, check_redline, compute_fingerprint, get_screen_metrics, pil_to_data_uri


class TaskWorkerThread(QThread):
    sig_process_success = pyqtSignal(dict, str)
    sig_process_error = pyqtSignal(str)
    sig_redline_triggered = pyqtSignal(str)
    sig_progress = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""

    def request_process(self, query: str):
        if self.isRunning():
            print("[TaskWorker] 上一个任务仍在处理中")
            return False
        self.query = query
        self.start()
        return True

    def run(self):
        try:
            self.sig_progress.emit(10, "捕获屏幕...")
            screenshot = capture_screen()
            if screenshot is None:
                self.sig_process_error.emit("屏幕捕获失败")
                return

            if check_redline(self.query):
                self.sig_redline_triggered.emit(
                    "⚠️ 触发安全红线：HAJIMI 仅提供操作指引，不执行自动点击等违规操作。"
                )
                return

            fingerprint = compute_fingerprint(screenshot)
            sw, sh = screenshot.size

            self.sig_progress.emit(40, "请求 AI 理解...")
            image_uri = pil_to_data_uri(screenshot)
            response = api_process(
                self.query,
                image_uri,
                window_title="桌面",
                screen_width=sw,
                screen_height=sh,
            )

            if not response.get("success"):
                self.sig_process_error.emit("服务端处理失败")
                return

            steps = response.get("steps") or []
            if not steps:
                self.sig_process_error.emit("未生成操作步骤")
                return

            self.sig_progress.emit(100, "完成")
            response["_screen_size"] = [sw, sh]
            response["_screen_metrics"] = get_screen_metrics()
            ref = response.get("reference_resolution")
            if ref and len(ref) >= 2:
                response["_ref_size"] = [int(ref[0]), int(ref[1])]
            self.sig_process_success.emit(response, fingerprint)

        except ApiError as exc:
            self.sig_process_error.emit(str(exc))
        except Exception as exc:
            self.sig_process_error.emit(str(exc))
