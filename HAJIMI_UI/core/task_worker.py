import time
from concurrent.futures import ThreadPoolExecutor

from PyQt5.QtCore import QThread, pyqtSignal

from config import DEPLOYMENT_MODE
from core.api_client import ApiError, process as api_process
from core.assist_collect import gather_assist_bundle
from core.assist_collect.gather import foreground_window_title
from core.screen_utils import (
    capture_screen,
    capture_screen_cached,
    check_redline,
    compute_fingerprint,
    downscale_for_api,
    get_locate_upload_max_side,
    get_screen_metrics,
    get_upload_jpeg_quality,
    get_upload_max_side,
    pil_to_data_uri,
)
from core.user_settings import load_user_settings
from core.routing_config import get_routing_mode, routing_needs_omniparser


def _process_error_hint(msg: str) -> str:
    from core.routing_config import routing_needs_omniparser

    if not routing_needs_omniparser():
        if "未启动" in msg or "不可达" in msg or "未连接" in msg:
            return (
                f"{msg} "
                "（L4 只需 A 端 + LLM；设置页「启动 A 端」或 scripts\\start_l4_demo.bat）"
            )
        if "LLM" in msg:
            return f"{msg} 请在设置填写 daseinai API Key，并确认 LLM_WIRE_API=responses。"
        if "chat/completions" in msg or "/responses" in msg:
            return (
                f"{msg} "
                "（LLM API 配置问题，非 A 端未启动；"
                "daseinai 需 LLM_WIRE_API=responses 并重启 A 端）"
            )
        return msg

    base = msg
    if DEPLOYMENT_MODE == "gpu_api":
        if "超时" in msg or "timed out" in msg.lower():
            base = (
                f"{msg} 可能卡在 A 端 :8010 或 OmniParser :9800，尚未调用 OpenAI。"
                "请运行设置页「链路诊断」。"
            )
        elif "未启动" in msg or "不可达" in msg:
            base = f"{msg} 请确认 :8010 A 端已启动。"
    return base


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
            screenshot, _cache_hit = capture_screen_cached(max_age_ms=900)
            if screenshot is None:
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
            speed_mode = load_user_settings().get("llm_speed_mode", "fast")
            routing = get_routing_mode()
            l4_path = not routing_needs_omniparser(routing)
            l4_path = not routing_needs_omniparser(routing)
            max_side = get_locate_upload_max_side(self.query)
            upload_img = downscale_for_api(screenshot, max_side)
            if upload_img.size != screenshot.size:
                print(
                    f"[TaskWorker] upload downscale "
                    f"{sw}x{sh} -> {upload_img.size[0]}x{upload_img.size[1]} "
                    f"(max_side={max_side}, l4={l4_path})"
                )
            image_uri = pil_to_data_uri(
                upload_img, quality=get_upload_jpeg_quality()
            )

            self.sig_progress.emit(
                35,
                "A 端 L4 Vision 处理中…" if l4_path else "A 端处理中（Vision 快路径或 OmniParser）…",
            )

            with ThreadPoolExecutor(max_workers=1) as pool:
                metrics = get_screen_metrics()
                assist_bundle = gather_assist_bundle()
                win_title = foreground_window_title(assist_bundle)
                future = pool.submit(
                    api_process,
                    self.query,
                    image_uri,
                    win_title,
                    sw,
                    sh,
                    fingerprint,
                    capture_size=[sw, sh],
                    upload_size=[upload_img.size[0], upload_img.size[1]],
                    screen_metrics=metrics,
                    assist_bundle=assist_bundle,
                )
                waited = 0
                while not future.done():
                    if waited >= 25:
                        if l4_path:
                            progress_msg = "L4 Locator Vision 识图定位…"
                        elif speed_mode == "precision":
                            progress_msg = "gpt-5.5 识图规划…（精准模式）"
                        elif speed_mode == "balanced":
                            progress_msg = "文本 LLM 规划…（平衡模式）"
                        else:
                            progress_msg = "DeepSeek 文本规划…（快速模式）"
                        self.sig_progress.emit(60, progress_msg)
                    elif waited >= 10:
                        self.sig_progress.emit(
                            50,
                            "A 端 L4 Planner 规划中…" if l4_path else "A 端处理中（GPU parse + LLM）…",
                        )
                    elif not l4_path:
                        self.sig_progress.emit(
                            40 + min(waited, 8),
                            "OmniParser 检测 UI 元素（GPU :9800）…",
                        )
                    else:
                        self.sig_progress.emit(
                            40 + min(waited, 8),
                            "A 端 L4 Vision 处理中…",
                        )
                    time.sleep(1)
                    waited += 1
                response = future.result()

            if not response.get("success"):
                self.sig_process_error.emit("服务端处理失败")
                return

            steps = response.get("steps") or []
            if not steps:
                self.sig_process_error.emit("未生成操作步骤")
                return

            meta = response.get("detection_meta") or {}
            llm_called = meta.get("llm_called")
            route = meta.get("route", "?")
            parse_ms = meta.get("parse_latency_ms")
            llm_ms = meta.get("llm_latency_ms")
            breakdown = meta.get("latency_breakdown") or {}
            total_ms = breakdown.get("total_ms")
            done_msg = f"完成（route={route}"
            if llm_called is not None:
                done_msg += f", llm={'是' if llm_called else '否'}"
            if parse_ms is not None:
                done_msg += f", parse={parse_ms}ms"
            if llm_ms is not None:
                done_msg += f", llm={llm_ms}ms"
            if total_ms is not None:
                done_msg += f", total={total_ms}ms"
            done_msg += "）"
            self.sig_progress.emit(100, done_msg)

            response["_screen_size"] = [sw, sh]
            response["_screen_metrics"] = get_screen_metrics()
            ref = response.get("reference_resolution")
            if ref and len(ref) >= 2:
                response["_ref_size"] = [int(ref[0]), int(ref[1])]
            self.sig_process_success.emit(response, fingerprint)

        except ApiError as exc:
            self.sig_process_error.emit(_process_error_hint(str(exc)))
        except Exception as exc:
            self.sig_process_error.emit(_process_error_hint(str(exc)))
