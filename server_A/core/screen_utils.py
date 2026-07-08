import base64
import hashlib
from io import BytesIO
from typing import Any, Dict, Optional

from PIL import Image, ImageGrab

try:
    import mss
except ImportError:
    mss = None

REDLINE_KEYWORDS = [
    "自动点击", "帮我执行", "替我操作", "自动抢票",
    "扫描硬盘", "查看聊天记录", "找出所有照片",
    "跟踪动态", "监控屏幕", "辅助代刷", "抢票",
]


def get_screen_metrics() -> Dict[str, Any]:
    """主屏逻辑/物理分辨率与 DPR（用于截图坐标 → 覆盖层坐标）。"""
    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app and app.primaryScreen():
            screen = app.primaryScreen()
            geo = screen.geometry()
            dpr = float(screen.devicePixelRatio())
            lw, lh = geo.width(), geo.height()
            return {
                "logical_w": lw,
                "logical_h": lh,
                "dpr": dpr,
                "physical_w": int(round(lw * dpr)),
                "physical_h": int(round(lh * dpr)),
            }
    except Exception:
        pass
    return {
        "logical_w": 1920,
        "logical_h": 1080,
        "dpr": 1.0,
        "physical_w": 1920,
        "physical_h": 1080,
    }


def capture_screen() -> Optional[Image.Image]:
    if mss is not None:
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        except Exception as exc:
            print(f"[CAP] mss 截图失败: {exc}")

    try:
        return ImageGrab.grab()
    except Exception as exc:
        print(f"[CAP] ImageGrab 截图失败: {exc}")
        return None


def compute_fingerprint(img: Image.Image) -> str:
    resized = img.resize((64, 64))
    return hashlib.sha256(resized.tobytes()).hexdigest()[:16]


def check_redline(query: str) -> bool:
    q_lower = query.lower()
    return any(kw in q_lower for kw in REDLINE_KEYWORDS)


def pil_to_data_uri(img: Image.Image) -> str:
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"
