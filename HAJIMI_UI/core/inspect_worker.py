from PyQt5.QtCore import QThread, pyqtSignal, QElapsedTimer

from config import DEPLOYMENT_MODE, INSPECT_TIMEOUT
from core.api_client import ApiError, inspect as api_inspect
from core.screen_utils import capture_screen, pil_to_data_uri, downscale_for_api, get_upload_max_side


def _inspect_progress_message() -> str:
    if DEPLOYMENT_MODE == "gpu_api":
        return "正在检测 UI 元素（A 端 :8010 → GPU :9800，约 2–10 秒）…"
    if DEPLOYMENT_MODE == "intranet":
        return "正在检测 UI 元素（远程 A 端，请稍候）…"
    return "正在检测 UI 元素（CPU 约 2–4 分钟，请勿重复点击）…"


def _inspect_error_hint(msg: str) -> str:
    hint = "（inspect 不产生 OpenAI 计费；设置页「链路诊断」可查看 :8010/:9800）"
    if DEPLOYMENT_MODE == "gpu_api":
        if "超时" in msg or "timed out" in msg.lower():
            return (
                f"{msg} 可能 A 端 :8010 阻塞或 :9800 隧道未就绪。{hint}"
            )
        if "8010" in msg or "A 端" in msg or "9800" in msg:
            return f"{msg} {hint}"
    return f"{msg} {hint}" if "链路诊断" not in msg else msg


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
            self.sig_progress.emit(15, _inspect_progress_message())
            upload = downscale_for_api(screenshot, get_upload_max_side(for_inspect=True))
            if upload.size != screenshot.size:
                print(
                    f"[inspect] downscale {sw}x{sh} -> "
                    f"{upload.size[0]}x{upload.size[1]}"
                )
            image_uri = pil_to_data_uri(upload, quality=85)
            print(
                f"[inspect] POST /api/demo/inspect timeout={INSPECT_TIMEOUT}s "
                f"(no OpenAI billing on this path)"
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
            self.sig_progress.emit(100, f"完成（{elapsed}s，无 LLM 调用）")
            self.sig_inspect_success.emit(data)

        except ApiError as exc:
            print(f"[inspect] FAIL ApiError: {exc}")
            self.sig_inspect_error.emit(_inspect_error_hint(str(exc)))
        except Exception as exc:
            print(f"[inspect] FAIL {type(exc).__name__}: {exc}")
            self.sig_inspect_error.emit(_inspect_error_hint(str(exc)))
