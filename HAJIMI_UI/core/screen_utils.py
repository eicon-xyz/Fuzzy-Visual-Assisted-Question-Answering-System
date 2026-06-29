import base64
import hashlib
from io import BytesIO
from typing import Optional

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
