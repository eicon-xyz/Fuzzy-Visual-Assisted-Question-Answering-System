from PyQt5.QtCore import QThread, pyqtSignal

from config import PROCESS_TIMEOUT
from core.api_client import ApiError, relocate_step as api_relocate
from core.screen_utils import capture_screen, get_screen_metrics, pil_to_data_uri


class RelocateWorkerThread(QThread):
    sig_relocate_success = pyqtSignal(dict)
    sig_relocate_error = pyqtSignal(str)
    sig_progress = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task_id = ""
        self.step_index = 1

    def request_relocate(self, task_id: str, step_index: int) -> bool:
        if self.isRunning():
            return False
        self.task_id = task_id
        self.step_index = step_index
        self.start()
        return True

    def run(self):
        try:
            self.sig_progress.emit(10, "捕获当前画面…")
            screenshot = capture_screen()
            if screenshot is None:
                self.sig_relocate_error.emit("屏幕捕获失败")
                return

            sw, sh = screenshot.size
            self.sig_progress.emit(
                30,
                "正在分析新画面并定位目标（CPU 约 2–4 分钟）…",
            )
            print(
                f"[relocate] POST /relocate step={self.step_index} "
                f"timeout={PROCESS_TIMEOUT}s"
            )
            data = api_relocate(
                self.task_id,
                self.step_index,
                pil_to_data_uri(screenshot),
                screen_width=sw,
                screen_height=sh,
            )
            data["_screen_size"] = [sw, sh]
            data["_screen_metrics"] = get_screen_metrics()
            ref = data.get("reference_resolution")
            if ref and len(ref) >= 2:
                data["_ref_size"] = [int(ref[0]), int(ref[1])]
            self.sig_progress.emit(100, "定位完成")
            self.sig_relocate_success.emit(data)

        except ApiError as exc:
            print(f"[relocate] FAIL ApiError: {exc}")
            self.sig_relocate_error.emit(str(exc))
        except Exception as exc:
            print(f"[relocate] FAIL {type(exc).__name__}: {exc}")
            self.sig_relocate_error.emit(str(exc))
