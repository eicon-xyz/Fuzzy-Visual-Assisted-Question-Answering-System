from PyQt5.QtCore import QThread, pyqtSignal

from config import PROCESS_TIMEOUT
from core.api_client import ApiError, relocate_step as api_relocate
from core.assist_collect import gather_assist_bundle
from core.screen_utils import (
    capture_screen,
    downscale_for_api,
    get_locate_upload_max_side,
    get_screen_metrics,
    get_upload_jpeg_quality,
    pil_to_data_uri,
)


class RelocateWorkerThread(QThread):
    sig_relocate_success = pyqtSignal(dict)
    sig_relocate_error = pyqtSignal(str)
    sig_progress = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task_id = ""
        self.step_index = 1
        self._step_text = ""

    def request_relocate(
        self, task_id: str, step_index: int, step_text: str = ""
    ) -> bool:
        if self.isRunning():
            return False
        self.task_id = task_id
        self.step_index = step_index
        self._step_text = step_text or ""
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
            max_side = get_locate_upload_max_side(self._step_text)
            upload = downscale_for_api(screenshot, max_side)
            metrics = get_screen_metrics()
            assist_bundle = gather_assist_bundle()
            self.sig_progress.emit(
                30,
                "正在 Vision 定位目标…",
            )
            print(
                f"[relocate] POST /relocate step={self.step_index} "
                f"upload={upload.size[0]}x{upload.size[1]} "
                f"timeout={PROCESS_TIMEOUT}s"
            )
            data = api_relocate(
                self.task_id,
                self.step_index,
                pil_to_data_uri(upload, quality=get_upload_jpeg_quality()),
                screen_width=sw,
                screen_height=sh,
                capture_size=[sw, sh],
                upload_size=[upload.size[0], upload.size[1]],
                screen_metrics=metrics,
                assist_bundle=assist_bundle,
            )
            if data.get("success") is False:
                self.sig_relocate_error.emit(
                    "Vision 未找到目标，请确认目标已在当前画面可见"
                )
                return
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
