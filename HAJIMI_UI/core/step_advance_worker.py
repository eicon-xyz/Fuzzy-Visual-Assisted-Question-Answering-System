"""后台线程执行蓝图步骤推进，避免 Vision locate / API 阻塞 Qt 主线程。"""
from __future__ import annotations

import time
from typing import List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from core.api_client import ApiError, advance_step as api_advance_step
from core.assist_collect import gather_assist_bundle
from core.screen_utils import (
    capture_screen,
    capture_screen_cached,
    compute_fingerprint,
    downscale_for_api,
    get_locate_upload_max_side,
    get_screen_metrics,
    get_upload_jpeg_quality,
    pil_to_data_uri,
)
from core.step_advance_progress import advance_locate_message


class StepAdvanceWorkerThread(QThread):
    sig_step_success = pyqtSignal(dict)
    sig_step_error = pyqtSignal(str)
    sig_progress = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_id = ""
        self._step_index = 1
        self._fingerprint = ""
        self._action = "advance"
        self._task_route: Optional[str] = None
        self._steps: List[dict] = []

    def _advance_locate_step_text(self) -> str:
        """advance 后 A 端将对下一步做 Vision 定位。"""
        idx = self._step_index
        if 0 <= idx < len(self._steps):
            step = self._steps[idx]
            return " ".join(
                filter(
                    None,
                    [
                        step.get("target"),
                        step.get("description"),
                        step.get("action"),
                    ],
                )
            )
        return ""

    def request_step(
        self,
        task_id: str,
        step_index: int,
        fingerprint: str,
        action: str,
        steps: List[dict],
        *,
        task_route: Optional[str] = None,
    ) -> bool:
        if self.isRunning():
            print("[StepWorker] 上一个步骤操作仍在处理中")
            return False
        self._task_id = task_id
        self._step_index = step_index
        self._fingerprint = fingerprint or ""
        self._action = action
        self._task_route = task_route
        self._steps = list(steps or [])
        self.start()
        return True

    def run(self):
        action = self._action
        try:
            self.sig_progress.emit(10, "准备步骤操作…")

            fingerprint = self._fingerprint
            shot, _ = capture_screen_cached(max_age_ms=900)
            if shot is None:
                shot = capture_screen()
            if shot is not None:
                fingerprint = compute_fingerprint(shot)

            image_uri: Optional[str] = None
            capture_size = None
            upload_size = None
            screen_metrics = None
            assist_bundle = None

            if action == "advance" and shot is not None:
                self.sig_progress.emit(25, "捕获当前画面…")
                locate_text = self._advance_locate_step_text()
                max_side = get_locate_upload_max_side(locate_text)
                upload = downscale_for_api(shot, max_side)
                image_uri = pil_to_data_uri(upload, quality=get_upload_jpeg_quality())
                capture_size = [shot.size[0], shot.size[1]]
                upload_size = [upload.size[0], upload.size[1]]
                screen_metrics = get_screen_metrics()
                assist_bundle = gather_assist_bundle()

            locate_msg = advance_locate_message(
                self._task_route,
                action,
                has_screenshot=bool(image_uri),
            )
            self.sig_progress.emit(40, locate_msg)

            t0 = time.perf_counter()
            response = api_advance_step(
                self._task_id,
                self._step_index,
                fingerprint,
                action,
                self._steps,
                image_data_uri=image_uri,
                capture_size=capture_size,
                upload_size=upload_size,
                screen_metrics=screen_metrics,
                assist_bundle=assist_bundle,
            )
            elapsed = int((time.perf_counter() - t0) * 1000)
            self.sig_progress.emit(100, f"步骤完成 ({elapsed}ms)")
            if capture_size:
                response["_screen_size"] = capture_size
            if upload_size:
                response["_upload_size"] = upload_size
            if screen_metrics:
                response["_screen_metrics"] = screen_metrics
            self.sig_step_success.emit(response)

        except ApiError as exc:
            print(f"[StepWorker] FAIL ApiError: {exc}")
            self.sig_step_error.emit(str(exc))
        except Exception as exc:
            print(f"[StepWorker] FAIL {type(exc).__name__}: {exc}")
            self.sig_step_error.emit(str(exc))
