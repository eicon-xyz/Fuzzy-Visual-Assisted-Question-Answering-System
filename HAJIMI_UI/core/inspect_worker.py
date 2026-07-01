from PyQt5.QtCore import QThread, pyqtSignal, QElapsedTimer

from config import INSPECT_TIMEOUT
from core.api_client import ApiError, inspect as api_inspect
from core.screen_utils import capture_screen, pil_to_data_uri


class InspectWorkerThread(QThread):
    sig_inspect_success = pyqtSignal(dict)
    sig_inspect_error = pyqtSignal(str)
    sig_progress = pyqtSignal(int, str)

    def run(self):
        timer = QElapsedTimer()
        timer.start()
        try:
            self.sig_progress.emit(5, "捕获屏幕…")
            screenshot = capture_screen()
            if screenshot is None:
                print("[inspect] FAIL: screen capture returned None")
                self.sig_inspect_error.emit("屏幕捕获失败")
                return

            sw, sh = screenshot.size
            print(f"[inspect] capture {sw}x{sh}")
            self.sig_progress.emit(
                15,
                "正在检测 UI 元素（CPU 约 2–4 分钟，请勿重复点击）…",
            )
            image_uri = pil_to_data_uri(screenshot)
            print(
                f"[inspect] POST /api/demo/inspect timeout={INSPECT_TIMEOUT}s "
                f"(expect OmniParser start parsing... within ~10s)"
            )
            data = api_inspect(image_uri, screen_width=sw, screen_height=sh)

            if not data.get("success"):
                self.sig_inspect_error.emit("检验检测失败")
                return

            elements = data.get("ui_elements") or []
            if not elements:
                self.sig_inspect_error.emit("未检测到 UI 元素")
                return

            data["_screen_size"] = [sw, sh]
            elapsed = timer.elapsed() // 1000
            self.sig_progress.emit(100, f"完成（{elapsed}s）")
            self.sig_inspect_success.emit(data)

        except ApiError as exc:
            print(f"[inspect] FAIL ApiError: {exc}")
            self.sig_inspect_error.emit(str(exc))
        except Exception as exc:
            print(f"[inspect] FAIL {type(exc).__name__}: {exc}")
            self.sig_inspect_error.emit(str(exc))
