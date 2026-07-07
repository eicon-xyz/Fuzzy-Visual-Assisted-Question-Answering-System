import base64
import hashlib
import threading
import time
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

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


_CAPTURE_CACHE: Dict[str, Any] = {
    "ts_ms": 0.0,
    "image": None,
    "lock": threading.Lock(),
    "event": threading.Event(),
}


def capture_screen_cached(max_age_ms: int = 900) -> Tuple[Optional[Image.Image], bool]:
    """
    带 TTL 缓存的截图；并发调用复用同一次 capture（in-flight 去重）。

    Returns:
        (image, cache_hit)
    """
    now = time.time() * 1000.0
    with _CAPTURE_CACHE["lock"]:
        cached = _CAPTURE_CACHE.get("image")
        ts = float(_CAPTURE_CACHE.get("ts_ms") or 0)
        if cached is not None and (now - ts) <= max_age_ms:
            return cached.copy(), True
        if _CAPTURE_CACHE.get("inflight"):
            waiter = True
        else:
            _CAPTURE_CACHE["inflight"] = True
            _CAPTURE_CACHE["event"].clear()
            waiter = False

    if waiter:
        _CAPTURE_CACHE["event"].wait(timeout=2.0)
        with _CAPTURE_CACHE["lock"]:
            cached = _CAPTURE_CACHE.get("image")
            if cached is not None:
                return cached.copy(), True
        return capture_screen(), False

    try:
        img = capture_screen()
        with _CAPTURE_CACHE["lock"]:
            if img is not None:
                _CAPTURE_CACHE["image"] = img
                _CAPTURE_CACHE["ts_ms"] = time.time() * 1000.0
            return (img.copy() if img else None), False
    finally:
        with _CAPTURE_CACHE["lock"]:
            _CAPTURE_CACHE["inflight"] = False
            _CAPTURE_CACHE["event"].set()


def compute_fingerprint(img: Image.Image) -> str:
    resized = img.resize((64, 64))
    return hashlib.sha256(resized.tobytes()).hexdigest()[:16]


def check_redline(query: str) -> bool:
    q_lower = query.lower()
    return any(kw in q_lower for kw in REDLINE_KEYWORDS)


_DESKTOP_ICON_KEYWORDS = (
    "桌面",
    "图标",
    "快捷方式",
    "icon",
    "shortcut",
    "chrome",
    "google",
    "回收站",
    "dev-c++",
    "devc++",
)

_DESKTOP_ICON_UPLOAD_MIN = 1920


def is_desktop_icon_step(step_text: str) -> bool:
    text = (step_text or "").lower()
    return any(k in text for k in _DESKTOP_ICON_KEYWORDS)


def get_locate_upload_max_side(step_text: str = "") -> int:
    """桌面小图标定位时提高上传分辨率。"""
    base = get_upload_max_side(for_l4=True)
    if is_desktop_icon_step(step_text):
        return max(base, _DESKTOP_ICON_UPLOAD_MIN)
    return base


def get_upload_max_side(*, for_inspect: bool = False, for_l4: bool | None = None) -> int:
    """Unified screenshot max side from env / defaults."""
    try:
        from config import INSPECT_MAX_SIDE, L4_UPLOAD_MAX_SIDE, SCREENSHOT_MAX_SIDE
    except Exception:
        return 960 if for_inspect else 720

    if for_inspect:
        return INSPECT_MAX_SIDE

    if for_l4 is None:
        try:
            from core.routing_config import routing_needs_omniparser

            for_l4 = not routing_needs_omniparser()
        except Exception:
            for_l4 = False

    if for_l4:
        return L4_UPLOAD_MAX_SIDE
    return SCREENSHOT_MAX_SIDE


def get_upload_jpeg_quality(*, for_l4: bool | None = None) -> int:
    if for_l4 is None:
        try:
            from core.routing_config import routing_needs_omniparser

            for_l4 = not routing_needs_omniparser()
        except Exception:
            for_l4 = False
    return 88 if for_l4 else 82


def downscale_for_api(img: Image.Image, max_side: Optional[int] = None) -> Image.Image:
    """B 端上传前缩小截图，减轻 GPU parse 与 HTTP 传输压力。"""
    if max_side is None:
        max_side = get_upload_max_side()
    w, h = img.size
    longest = max(w, h)
    if longest <= max_side:
        return img
    ratio = max_side / longest
    nw, nh = max(1, int(w * ratio)), max(1, int(h * ratio))
    work = img.convert("RGB") if img.mode not in ("RGB",) else img.copy()
    return work.resize((nw, nh), Image.Resampling.LANCZOS)


def pil_to_data_uri(img: Image.Image, *, format: str = "JPEG", quality: int = 85) -> str:
    buffer = BytesIO()
    if format.upper() == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    if format.upper() == "JPEG":
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        mime = "image/jpeg"
    else:
        img.save(buffer, format="PNG")
        mime = "image/png"
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"
