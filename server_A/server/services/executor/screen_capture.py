"""屏幕/窗口抓取。两个通道，许可要求不同。

| 通道 | 实现 | 是否碰用户屏幕 | 许可 |
|---|---|---|---|
| 窗口 | ``PrintWindow(hwnd, PW_RENDERFULLCONTENT)`` | 否（被动读该窗口） | 不需要 |
| 整屏 | ``mss.grab(monitors[1])`` | 是（会看到窗口之外的一切） | ``FULLSCREEN_GRAB`` |

``Frame`` 把图像和它的原点绑定在一起：图像像素 (0,0) 对应屏幕坐标 ``origin``。
调用方因此不可能拿错坐标系——这是 I4 的载体。

窗口通道顺带删除了一整套按标题涂黑的 hack（``Python``/``Code``/``Terminal``…）：
那套东西存在的唯一理由是截图是整屏的，而它会把被测窗口自己涂黑。
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw

from server.services.executor.permit import ForegroundAction, ForegroundPermit

logger = logging.getLogger(__name__)

__all__ = [
    "CaptureFailure",
    "Frame",
    "capture_fullscreen",
    "capture_window",
]

# 整屏兜底路径专用的涂黑名单：只在这里生效
_BLACKOUT_PATTERNS = [
    "HAJIMI",
    "hajimi",
    "uvicorn",
    "server.main:app",
    "Windows PowerShell",
    "powershell.exe",
    "Command Prompt",
    "cmd.exe",
    "MINGW",
    "msys2",
]


class CaptureFailure:
    NONE = "none"
    WINDOW_GONE = "window_gone"
    MINIMIZED = "minimized"
    ZERO_SIZE = "zero_size"
    PRINTWINDOW_FAILED = "printwindow_failed"
    BLACK_FRAME = "black_frame"
    NO_PERMIT = "no_permit"


@dataclass(frozen=True)
class Frame:
    """一次抓取的结果。``image is None`` 时 ``failure`` 说明原因。"""

    image: Optional[Image.Image]
    origin: Tuple[int, int]
    channel: str  # "print_window" | "screen_fallback" | "none"
    failure: str = CaptureFailure.NONE

    @property
    def available(self) -> bool:
        return self.image is not None

    def to_screen(self, rel: Tuple[int, int]) -> Tuple[int, int]:
        """窗口相对 → 屏幕绝对。全仓唯一的坐标换算点（I4）。"""
        return (self.origin[0] + int(rel[0]), self.origin[1] + int(rel[1]))

    def to_data_url(self, fmt: str = "JPEG", max_edge: int = 1024) -> Optional[str]:
        if self.image is None:
            return None
        img = self.image
        if fmt == "JPEG" and max(img.size) > max_edge:
            r = max_edge / max(img.size)
            img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
        buf = BytesIO()
        if fmt == "JPEG":
            img.convert("RGB").save(buf, format="JPEG", quality=75)
            mime = "image/jpeg"
        else:
            img.save(buf, format="PNG")
            mime = "image/png"
        return f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode()}"


def _blank_reason(img: Optional[Image.Image]) -> Optional[str]:
    """PrintWindow 返回 True 但像素恒定时判为失败。

    Chromium/Electron/受保护内容常见：PrintWindow 成功但整张纯黑。采样步长 7，
    1080p 一张图 <2ms。
    """
    if img is None:
        return CaptureFailure.PRINTWINDOW_FAILED
    try:
        small = img.resize((max(1, img.width // 7), max(1, img.height // 7)))
        extrema = small.convert("L").getextrema()
        if extrema[1] - extrema[0] <= 2:
            return CaptureFailure.BLACK_FRAME
    except Exception:  # pragma: no cover
        return None
    return None


def capture_window(
    rect: Tuple[int, int, int, int],
    hwnd: int,
) -> Frame:
    """按窗口抓取（PrintWindow）。被动只读，不需要许可。

    Args:
        rect: UIA 顶层控件的 ``BoundingRectangle``（屏幕绝对 L,T,R,B）。
              输出图像的 origin 就是它的左上角——投影 bbox 与图像同原点。
        hwnd: 目标窗口句柄。
    """
    left, top, right, bottom = (int(v) for v in rect)
    if right <= left or bottom <= top:
        return Frame(None, (left, top), "none", CaptureFailure.ZERO_SIZE)

    try:
        import ctypes

        import win32gui
        import win32ui

        if not hwnd or not win32gui.IsWindow(hwnd):
            return Frame(None, (left, top), "none", CaptureFailure.WINDOW_GONE)
        if win32gui.IsIconic(hwnd):
            # 最小化窗口 PrintWindow 必空，且 restore 会改屏幕状态 → 不在抓取层做
            return Frame(None, (left, top), "none", CaptureFailure.MINIMIZED)

        wl, wt, wr, wb = win32gui.GetWindowRect(hwnd)
        w, h = wr - wl, wb - wt
        if w <= 0 or h <= 0:
            return Frame(None, (left, top), "none", CaptureFailure.ZERO_SIZE)

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)
        try:
            ok = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
            if not ok:
                ok = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 0)
            if not ok:
                logger.debug(
                    "PrintWindow failed hwnd=%s size=%sx%s", hwnd, w, h
                )
                return Frame(None, (left, top), "none", CaptureFailure.PRINTWINDOW_FAILED)
            info = bmp.GetInfo()
            bits = bmp.GetBitmapBits(True)
            img = Image.frombuffer(
                "RGB",
                (info["bmWidth"], info["bmHeight"]),
                bits,
                "raw",
                "BGRX",
                0,
                1,
            )
        finally:
            win32gui.DeleteObject(bmp.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)

        # Win10/11 有约 7px 隐形边框：GetWindowRect ≠ UIA BoundingRectangle。
        # 不裁剪会让图像与投影系统性错位（LLM 会在错位置描述界面）。
        dx, dy = left - wl, top - wt
        if dx or dy or img.width != (right - left) or img.height != (bottom - top):
            img = img.crop((dx, dy, dx + (right - left), dy + (bottom - top)))

        failure = _blank_reason(img)
        if failure:
            logger.debug("PrintWindow blank hwnd=%s reason=%s", hwnd, failure)
            return Frame(None, (left, top), "none", failure)

        return Frame(img, (left, top), "print_window", CaptureFailure.NONE)
    except ImportError:  # pragma: no cover - 非 Windows
        return Frame(None, (left, top), "none", CaptureFailure.PRINTWINDOW_FAILED)
    except Exception as exc:  # pragma: no cover
        logger.debug("capture_window failed hwnd=%s: %s", hwnd, exc)
        return Frame(None, (left, top), "none", CaptureFailure.PRINTWINDOW_FAILED)


def _find_self_windows() -> List[Tuple[int, int, int, int]]:
    """整屏兜底路径用：按标题找自身/开发工具窗口，涂黑。"""
    try:
        import win32gui
    except ImportError:  # pragma: no cover
        return []

    rects: List[Tuple[int, int, int, int]] = []

    def callback(hwnd, _ctx):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return
            if not any(p.lower() in title.lower() for p in _BLACKOUT_PATTERNS):
                return
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 100 or h < 50:
                return
            if rect[0] < -1000 or rect[1] < -1000:
                return
            rects.append(tuple(rect))
        except Exception:
            pass

    win32gui.EnumWindows(callback, None)
    return rects


def capture_fullscreen(
    permit: Optional[ForegroundPermit],
    rect: Optional[Tuple[int, int, int, int]] = None,
) -> Frame:
    """整屏抓取（会看到窗口之外的东西）→ 按 rect 裁剪。要求 FULLSCREEN_GRAB。

    无许可时返回 ``Frame(failure=NO_PERMIT)``——**不抛异常、不静默降级**，
    由调用方决定给模型看什么。
    """
    origin = (int(rect[0]), int(rect[1])) if rect else (0, 0)
    if permit is None or not permit.allows(ForegroundAction.FULLSCREEN_GRAB):
        return Frame(None, origin, "none", CaptureFailure.NO_PERMIT)
    try:
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = Image.frombytes(
                "RGB",
                (monitor["width"], monitor["height"]),
                sct.grab(monitor).bgra,
                "raw",
                "BGRX",
            )
    except Exception as exc:  # pragma: no cover
        logger.error("capture_fullscreen: %s", exc)
        return Frame(None, origin, "none", CaptureFailure.PRINTWINDOW_FAILED)

    if rect:
        left, top, right, bottom = (int(v) for v in rect)
        left = max(left, monitor.get("left", 0))
        top = max(top, monitor.get("top", 0))
        right = min(right, left + img.width)
        bottom = min(bottom, top + img.height)
        if right > left and bottom > top:
            img = img.crop((left, top, right, bottom))

    draw = ImageDraw.Draw(img)
    ml, mt = monitor.get("left", 0), monitor.get("top", 0)
    for bl, bt, br, bb in _find_self_windows():
        x1, y1 = max(0, bl - ml), max(0, bt - mt)
        x2, y2 = min(img.width, br - ml), min(img.height, bb - mt)
        if x2 > x1 and y2 > y1:
            draw.rectangle([x1, y1, x2, y2], fill="black")
    return Frame(img, origin, "screen_fallback", CaptureFailure.NONE)
