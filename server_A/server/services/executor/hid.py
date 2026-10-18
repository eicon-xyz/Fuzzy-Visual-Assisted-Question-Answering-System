"""进程内唯一的系统级输入出口（X 档）。

为什么单独一个模块
------------------
不是分层美学，是为了让"除本文件外无人 import 输入库"能写成一条**可执行的**
架构断言（``tests/test_phase1_hid_boundary.py``）。一旦有人为修急 bug 在
``agent.py`` 直接 ``import pyautogui``，那条测试立刻红；否则所有类型保证都只是叙事。

调用约定
--------
1. 每个公开函数首参是 ``permit``（无默认值）——新增函数忘了传，
   第一次调用就是 ``TypeError``，不会静默降级成"无授权也能点"。
2. 坐标系**只接受屏幕绝对坐标**。窗口相对 → 绝对 的换算发生在
   ``screen_capture.Frame.to_screen()``，不在这里（I4）。
3. 不做重试、不做坐标回退、不做模式降级。失败即返回，由调用方按 error_code 决策。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from server.services.executor.permit import ForegroundAction, ForegroundPermit

logger = logging.getLogger(__name__)

__all__ = [
    "HIDResult",
    "activate_window",
    "click",
    "drag",
    "hotkey",
    "move",
    "paste",
    "precheck",
    "press_key",
    "screen_size",
    "scroll",
    "set_focus",
    "typewrite",
]

# pydirectinput 在 Windows 上更快更可靠（走 SendInput），回退 pyautogui
try:
    import pydirectinput

    _USE_DIRECT = True
    pydirectinput.FAILSAFE = False
except ImportError:  # pragma: no cover - 依赖缺失时走 mock
    _USE_DIRECT = False

try:
    import pyautogui

    _HAS_PYAUTOGUI = True
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
except ImportError:  # pragma: no cover
    _HAS_PYAUTOGUI = False

if not _HAS_PYAUTOGUI and not _USE_DIRECT:  # pragma: no cover
    logger.warning("pydirectinput / pyautogui 均不可用 — hid 进入 mock 模式")

try:
    import pyperclip

    _HAS_PYPERCLIP = True
except ImportError:  # pragma: no cover
    _HAS_PYPERCLIP = False


@dataclass(frozen=True)
class HIDResult:
    ok: bool
    actions: tuple[ForegroundAction, ...] = ()
    error_code: Optional[str] = None
    error: Optional[str] = None
    hint: Optional[str] = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out: dict = {"success": self.ok}
        if not self.ok:
            out["action_ok"] = False
            if self.error_code:
                out["error_code"] = self.error_code
            if self.error:
                out["error"] = self.error
            if self.hint:
                out["hint"] = self.hint
        out.update(self.detail)
        return out


def precheck(
    permit: Optional[ForegroundPermit],
    required: tuple[ForegroundAction, ...],
    origin: str,
) -> Optional[dict]:
    """在**动手之前**确认许可，避免"抢完焦点才发现粘贴被拒"。

    返回 None 表示可执行；否则返回可直接回给模型的拒绝 dict。
    """
    denied = _guard(permit, required, origin)
    return None if denied is None else denied.to_dict()


_PERMIT_HINT = (
    "此路径会改光标/键盘焦点/剪贴板，需要本任务的接管许可。"
    "优先改走 UIA 语义路径：click(element_id) 而非坐标、type_text 走 ValuePattern、"
    "set_range 调数值、window_action 换窗口。若确无语义路径，"
    "调用 mark_step_failed 并说明需要接管桌面。"
)


def _guard(
    permit: Optional[ForegroundPermit],
    required: tuple[ForegroundAction, ...],
    origin: str,
) -> Optional[HIDResult]:
    """唯一的许可守卫。返回 None 表示放行。"""
    if permit is None:
        logger.info("[hid] denied origin=%s reason=no_permit", origin)
        return HIDResult(
            ok=False,
            actions=required,
            error_code="permit_required",
            error=f"takeover permit required for {origin}",
            hint=_PERMIT_HINT,
            detail={"required_actions": [a.value for a in required]},
        )
    if not permit.live:
        logger.info("[hid] denied origin=%s reason=expired", origin)
        return HIDResult(
            ok=False,
            actions=required,
            error_code="permit_revoked",
            error=f"takeover permit expired or revoked for task={permit.task_id}",
            hint="接管许可已失效（任务结束或超时）。停止 HID 动作，重新观察后只用 UIA 路径，不要重试。",
            detail={"required_actions": [a.value for a in required]},
        )
    missing = [a for a in required if a not in permit.actions]
    if missing:
        logger.info(
            "[hid] denied origin=%s reason=missing:%s granted=%s",
            origin,
            ",".join(a.value for a in missing),
            permit.as_list(),
        )
        return HIDResult(
            ok=False,
            actions=required,
            error_code="permit_required",
            error=(
                f"takeover permit lacks {','.join(a.value for a in missing)} "
                f"for {origin}"
            ),
            hint=_PERMIT_HINT,
            detail={
                "required_actions": [a.value for a in required],
                "granted_actions": permit.as_list(),
            },
        )
    return None


# ── 坐标 ────────────────────────────────────────────────────────────────────


def screen_size() -> tuple[int, int]:
    """当前主屏分辨率。

    旧 ``clicker._clamp_coord`` 用 1920×1080 硬编码默认值且调用方不传，
    在 1080p 以上的屏幕上会把坐标静默截断（2K 屏 x>1915 全被压到 1915）。
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        w = int(user32.GetSystemMetrics(0)) or 1920
        h = int(user32.GetSystemMetrics(1)) or 1080
        return w, h
    except Exception:  # pragma: no cover - 非 Windows / 无 ctypes
        return 1920, 1080


def _clamp(point: tuple[int, int], margin: int = 5) -> tuple[int, int]:
    x, y = int(point[0]), int(point[1])
    w, h = screen_size()
    x = max(margin, min(w - margin, x))
    y = max(margin, min(h - margin, y))
    return x, y


# ── 设备层原语（无许可检查，只由本模块公开函数调用）────────────────────────


def _move_raw(x: int, y: int, duration: float = 0.2) -> None:
    if _USE_DIRECT:
        pydirectinput.moveTo(x, y, duration=duration)
    elif _HAS_PYAUTOGUI:
        pyautogui.moveTo(x, y, duration=duration)
    else:  # pragma: no cover
        logger.info("mock move: (%s,%s)", x, y)


def _click_raw(button: str = "left", clicks: int = 1) -> None:
    if _USE_DIRECT:
        for _ in range(clicks):
            pydirectinput.click(button=button)
            time.sleep(0.1)
    elif _HAS_PYAUTOGUI:
        pyautogui.click(button=button, clicks=clicks)
    else:  # pragma: no cover
        logger.info("mock click: %s x%s", button, clicks)


def _hotkey_raw(*keys: str) -> None:
    if _USE_DIRECT:
        try:
            pydirectinput.hotkey(*keys)
            return
        except AttributeError:  # pragma: no cover - 老版本无 hotkey
            for k in keys:
                pydirectinput.keyDown(k)
            for k in reversed(keys):
                pydirectinput.keyUp(k)
            return
    if _HAS_PYAUTOGUI:
        pyautogui.hotkey(*keys)
    else:  # pragma: no cover
        logger.info("mock hotkey: %s", "+".join(keys))


# ── 公开 API ────────────────────────────────────────────────────────────────


def click(
    permit: Optional[ForegroundPermit],
    point: tuple[int, int],
    *,
    button: str = "left",
    clicks: int = 1,
) -> HIDResult:
    """在屏幕绝对坐标点击。"""
    denied = _guard(permit, (ForegroundAction.POINTER,), "hid.click")
    if denied is not None:
        return denied
    x, y = _clamp(point)
    _move_raw(x, y, duration=0.2)
    time.sleep(0.15)
    _click_raw(button=button, clicks=clicks)
    logger.info("hid.click (%s,%s) %s x%s", x, y, button, clicks)
    return HIDResult(
        ok=True,
        actions=(ForegroundAction.POINTER,),
        detail={"via": "coord", "x": x, "y": y, "button": button, "clicks": clicks},
    )


def move(
    permit: Optional[ForegroundPermit],
    point: tuple[int, int],
    duration: float = 0.3,
) -> HIDResult:
    denied = _guard(permit, (ForegroundAction.POINTER,), "hid.move")
    if denied is not None:
        return denied
    x, y = _clamp(point)
    _move_raw(x, y, duration=duration)
    return HIDResult(
        ok=True,
        actions=(ForegroundAction.POINTER,),
        detail={"via": "coord", "x": x, "y": y},
    )


def scroll(
    permit: Optional[ForegroundPermit],
    point: Optional[tuple[int, int]],
    amount: int = -3,
) -> HIDResult:
    """滚轮。``point=None`` 时在当前光标处滚动，不搬光标。"""
    denied = _guard(permit, (ForegroundAction.POINTER,), "hid.scroll")
    if denied is not None:
        return denied
    if point is not None:
        x, y = _clamp(point)
        _move_raw(x, y, duration=0.1)
        time.sleep(0.1)
    else:
        x, y = None, None
    if _USE_DIRECT:
        pydirectinput.scroll(amount)
    elif _HAS_PYAUTOGUI:
        if x is None:
            pyautogui.scroll(amount)
        else:
            pyautogui.scroll(amount, x=x, y=y)
    else:  # pragma: no cover
        logger.info("mock scroll: (%s,%s) %s", x, y, amount)
    return HIDResult(
        ok=True,
        actions=(ForegroundAction.POINTER,),
        detail={"via": "coord", "x": x, "y": y, "amount": amount},
    )


def drag(
    permit: Optional[ForegroundPermit],
    start: tuple[int, int],
    end: tuple[int, int],
    duration: float = 0.5,
) -> HIDResult:
    denied = _guard(permit, (ForegroundAction.POINTER,), "hid.drag")
    if denied is not None:
        return denied
    x1, y1 = _clamp(start)
    x2, y2 = _clamp(end)
    _move_raw(x1, y1, duration=0.2)
    if _USE_DIRECT:
        pydirectinput.mouseDown()
        pydirectinput.moveTo(x2, y2, duration=duration)
        pydirectinput.mouseUp()
    elif _HAS_PYAUTOGUI:
        pyautogui.drag(x2 - x1, y2 - y1, duration=duration)
    else:  # pragma: no cover
        logger.info("mock drag: (%s,%s)->(%s,%s)", x1, y1, x2, y2)
    return HIDResult(
        ok=True,
        actions=(ForegroundAction.POINTER,),
        detail={"via": "coord", "from": [x1, y1], "to": [x2, y2]},
    )


def hotkey(permit: Optional[ForegroundPermit], *keys: str) -> HIDResult:
    """组合键。按键会落到当前前台窗口，属 KEYBOARD。"""
    denied = _guard(permit, (ForegroundAction.KEYBOARD,), "hid.hotkey")
    if denied is not None:
        return denied
    _hotkey_raw(*keys)
    return HIDResult(
        ok=True,
        actions=(ForegroundAction.KEYBOARD,),
        detail={"via": "hid_key", "keys": "+".join(keys)},
    )


def press_key(
    permit: Optional[ForegroundPermit],
    key: str,
    hold_ms: int = 200,
) -> HIDResult:
    """单键按下+抬起。Win 键只能这样按（hotkey 在部分版本不可靠）。"""
    denied = _guard(permit, (ForegroundAction.KEYBOARD,), "hid.press_key")
    if denied is not None:
        return denied
    if _USE_DIRECT:
        pydirectinput.keyDown(key)
        time.sleep(hold_ms / 1000.0)
        pydirectinput.keyUp(key)
    elif _HAS_PYAUTOGUI:
        pyautogui.keyDown(key)
        time.sleep(hold_ms / 1000.0)
        pyautogui.keyUp(key)
    else:  # pragma: no cover
        logger.info("mock press_key: %s", key)
    return HIDResult(
        ok=True,
        actions=(ForegroundAction.KEYBOARD,),
        detail={"via": "hid_key", "key": key},
    )


def typewrite(
    permit: Optional[ForegroundPermit],
    text: str,
    interval: float = 0.03,
) -> HIDResult:
    """逐字符键入。IME 环境不可靠，优先用 ``paste``。"""
    denied = _guard(permit, (ForegroundAction.KEYBOARD,), "hid.typewrite")
    if denied is not None:
        return denied
    if _USE_DIRECT:
        pydirectinput.typewrite(text, interval=interval)
    elif _HAS_PYAUTOGUI:
        pyautogui.typewrite(text, interval=interval)
    else:  # pragma: no cover
        logger.info("mock type: %s", text[:30])
    return HIDResult(
        ok=True,
        actions=(ForegroundAction.KEYBOARD,),
        detail={"via": "hid_key", "length": len(text)},
    )


def paste(permit: Optional[ForegroundPermit], text: str) -> HIDResult:
    """写剪贴板 → ctrl+v → 还原剪贴板。

    剪贴板是全局资源（会改到用户的东西），所以 CLIPBOARD 与 KEYBOARD 双域。
    """
    required = (ForegroundAction.CLIPBOARD, ForegroundAction.KEYBOARD)
    denied = _guard(permit, required, "hid.paste")
    if denied is not None:
        return denied
    if not text:
        return HIDResult(ok=True, actions=required, detail={"via": "coord_clipboard"})
    if not _HAS_PYPERCLIP:  # pragma: no cover
        return typewrite(permit, text)
    if not _HAS_PYAUTOGUI and not _USE_DIRECT:  # pragma: no cover
        logger.info("mock paste: %s", text[:30])
        return HIDResult(ok=True, actions=required, detail={"via": "coord_clipboard"})
    old = pyperclip.paste()
    pyperclip.copy(text)
    # keyDown/keyUp 而非 hotkey：避免部分版本 hotkey bug
    if _USE_DIRECT:
        pydirectinput.keyDown("ctrl")
        time.sleep(0.05)
        pydirectinput.keyDown("v")
        time.sleep(0.1)
        pydirectinput.keyUp("v")
        pydirectinput.keyUp("ctrl")
    else:
        pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    try:
        pyperclip.copy(old)
    except Exception:
        logger.debug("clipboard restore failed", exc_info=True)
    return HIDResult(
        ok=True,
        actions=required,
        detail={"via": "coord_clipboard", "length": len(text)},
    )


def set_focus(permit: Optional[ForegroundPermit], control) -> HIDResult:
    """把键盘焦点交给某个 UIA 控件。

    全仓唯一的 ``SetFocus`` 调用点。U 档正常路径不该走到这里——它是
    "ValuePattern 缺失"时的降级边界，所以要 ACTIVATE。
    """
    denied = _guard(permit, (ForegroundAction.ACTIVATE,), "hid.set_focus")
    if denied is not None:
        return denied
    try:
        control.SetFocus()
    except Exception as exc:
        return HIDResult(
            ok=False,
            actions=(ForegroundAction.ACTIVATE,),
            error_code="hid_failed",
            error=f"SetFocus failed: {exc}",
            hint="控件可能已销毁或被禁用。先 get_screen_info 重新观察再决策。",
        )
    return HIDResult(
        ok=True,
        actions=(ForegroundAction.ACTIVATE,),
        detail={"via": "uia_window"},
    )


def activate_window(
    permit: Optional[ForegroundPermit],
    title_or_app: str,
    timeout_s: float = 2.0,
) -> HIDResult:
    """按标题把窗口提到前台（pygetwindow → pywinauto 回退）。"""
    denied = _guard(permit, (ForegroundAction.ACTIVATE,), "hid.activate_window")
    if denied is not None:
        return denied
    try:
        import pygetwindow as gw
    except ImportError:  # pragma: no cover
        return HIDResult(
            ok=False,
            actions=(ForegroundAction.ACTIVATE,),
            error_code="hid_failed",
            error="pygetwindow not installed",
        )

    deadline = time.time() + timeout_s
    target = None
    needle = (title_or_app or "").lower()
    while time.time() < deadline:
        try:
            cands = [w for w in gw.getAllWindows() if w.title and not w.title.startswith("_")]
        except Exception:
            cands = []
        exact = [w for w in cands if needle and needle == (w.title or "").lower()]
        fuzzy = [w for w in cands if needle and needle in (w.title or "").lower()]
        pool = exact or fuzzy
        if pool:
            target = max(pool, key=lambda w: max(1, w.width) * max(1, w.height))
            break
        time.sleep(0.1)

    if target is None:
        return HIDResult(
            ok=False,
            actions=(ForegroundAction.ACTIVATE,),
            error_code="window_not_found",
            error=f"no window matching '{title_or_app}'",
            hint="窗口可能还没渲染完：wait(1) 后重新 list（get_screen_info 的 windows 字段）再试。",
        )

    try:
        target.restore()
        time.sleep(0.2)
        target.activate()
        time.sleep(0.3)
        if getattr(target, "isActive", False):
            return HIDResult(
                ok=True,
                actions=(ForegroundAction.ACTIVATE,),
                detail={"via": "launcher", "window": target.title},
            )
        from pywinauto import Desktop

        Desktop(backend="win32").window(title=target.title).set_focus()
        return HIDResult(
            ok=True,
            actions=(ForegroundAction.ACTIVATE,),
            detail={"via": "launcher", "window": target.title, "method": "pywinauto"},
        )
    except Exception as exc:
        return HIDResult(
            ok=False,
            actions=(ForegroundAction.ACTIVATE,),
            error_code="hid_failed",
            error=f"activate_window failed: {exc}",
            hint="窗口可能已关闭。重新 list_windows 确认后再说。",
        )
