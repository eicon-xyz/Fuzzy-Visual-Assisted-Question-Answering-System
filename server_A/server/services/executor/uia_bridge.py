"""UIA 绑定桥 —— Windows UI Automation 结构化采集 + 精确操作。

背景：原依赖远程 OmniParser GPU(:9800) 做屏幕元素感知，已不可用。
本模块让执行 agent 的「屏幕感知 + 操作」改为：
  1. snapshot(): 遍历前台窗口 UIA 控件树 → HAJIMI UIElement 列表
     （name / control_type / bbox / 可用交互模式 / enabled）
  2. act(): 优先调用控件模式（Invoke / SelectionItem / Toggle /
     ExpandCollapse / ValuePattern.SetValue），失败回退控件 bbox 中心坐标点击
  3. verify(): 用控件状态（IsEnabled / IsOffscreen）+ 轮询做执行后校验

与像素框点击相比，UIA 绑定具有控件身份 + 确定性动作 + 状态校验，
可显著提升点击/输入的准确率（Q2 方案执行层第一档）。

设计要点：
  * 初始化 SetProcessDpiAwareness(2)，保证 UIA BoundingRectangle（物理像素）
    与 pyautogui/mss 坐标一致（DPI 缩放屏不错位）。
  * 非 Windows / 未安装 uiautomation / 前台窗口无可交互控件时优雅降级
    （snapshot 返回 []，由 agent 回退视觉/OmniParser 或明确报错）。
"""
from __future__ import annotations

import platform
import time
from typing import Dict, List, Optional, Tuple

from server.models.schemas import UIElement

logger = None  # lazy import to keep module import-light


def _log():
    global logger
    if logger is None:
        import logging

        logger = logging.getLogger(__name__)
    return logger


# ═══════════════════════════════════════════════════════════════════════════
# DPI 感知初始化（进程级，仅 Windows）
# ═══════════════════════════════════════════════════════════════════════════


def _ensure_dpi_aware() -> None:
    """SetProcessDpiAwareness(2)=PER_MONITOR_DPI_AWARE，幂等。失败静默。"""
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_ensure_dpi_aware()


def _import_auto():
    """返回 uiautomation 模块；不可用返回 None。"""
    try:
        import uiautomation as auto  # type: ignore

        return auto
    except Exception:
        return None


def _control_bbox(control) -> Optional[List[int]]:
    try:
        rect = control.BoundingRectangle
        if not rect:
            return None
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        if right <= left or bottom <= top:
            return None
        return [int(left), int(top), int(right), int(bottom)]
    except Exception:
        return None


def _control_type(control) -> str:
    try:
        name = (getattr(control, "ControlTypeName", "") or "").lower()
    except Exception:
        name = ""
    mapping = {
        "button": "button",
        "menuitem": "menu",
        "edit": "input",
        "document": "text",
        "text": "text",
        "combobox": "dropdown",
        "checkbox": "checkbox",
        "tabitem": "menu",
        "listitem": "menu",
        "hyperlink": "link",
    }
    for key, val in mapping.items():
        if key in name:
            return val
    return "text" if name in ("text", "static") else "other"


def _available_patterns(control) -> List[str]:
    """探测控件支持的 UIA 模式。"""
    out: List[str] = []
    for pname, getter in (
        ("invoke", "GetInvokePattern"),
        ("selectionitem", "GetSelectionItemPattern"),
        ("toggle", "GetTogglePattern"),
        ("expandcollapse", "GetExpandCollapsePattern"),
        ("value", "GetValuePattern"),
    ):
        try:
            if getattr(control, getter)() is not None:
                out.append(pname)
        except Exception:
            pass
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 桥接器
# ═══════════════════════════════════════════════════════════════════════════


class UIABridge:
    """UIA 采集 + 操作 + 校验。每个 ExecutionAgent 一个实例。"""

    _MAX_DEPTH = 5
    _MAX_NODES = 60

    def __init__(self) -> None:
        self._last_controls: Dict[str, object] = {}
        self._last_window_title: str = ""
        self._auto = _import_auto()
        self._available = self._auto is not None and platform.system() == "Windows"
        if not self._available:
            _log().info("UIA bridge unavailable (non-Windows or no uiautomation)")

    @property
    def available(self) -> bool:
        return self._available

    # ── 采集 ──

    def snapshot(self, max_depth: int = None, max_nodes: int = None) -> List[UIElement]:
        """遍历前台窗口 UIA 树，返回 UIElement 列表（含空间/模式信息）。"""
        self._last_controls = {}
        if not self._available:
            return []
        auto = self._auto
        depth = max_depth or self._MAX_DEPTH
        budget = [max_nodes or self._MAX_NODES]

        out: List[UIElement] = []
        try:
            fg = auto.GetForegroundControl()
            if fg is None:
                return []
            try:
                self._last_window_title = fg.Name or ""
            except Exception:
                pass
            self._walk(fg, 0, depth, budget, out)
        except Exception as exc:
            _log().debug("UIA snapshot failed: %s", exc)
        return out

    def _walk(
        self,
        control,
        depth: int,
        max_depth: int,
        budget: List[int],
        out: List[UIElement],
    ) -> None:
        if depth > max_depth or budget[0] <= 0:
            return
        budget[0] -= 1
        try:
            bbox = _control_bbox(control)
            if bbox is not None:
                name = (control.Name or "").strip()
                ctrl_type = _control_type(control)
                # 只保留有名字或可交互的控件，减少噪音
                if name or ctrl_type in ("button", "input", "checkbox", "dropdown", "link"):
                    cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
                    eid = f"u{len(self._last_controls) + 1}"
                    try:
                        enabled = bool(control.IsEnabled)
                    except Exception:
                        enabled = True
                    patterns = _available_patterns(control)
                    self._last_controls[eid] = control
                    out.append(
                        UIElement(
                            element_id=eid,
                            bbox=bbox,
                            element_type=ctrl_type,
                            text=name,
                            confidence=0.9,
                            center=[cx, cy],
                            left_elem_ids=[],
                            right_elem_ids=[],
                            top_elem_ids=[],
                            bottom_elem_ids=[],
                        )
                    )
            children = control.GetChildren()
            for child in children:
                if budget[0] <= 0:
                    break
                self._walk(child, depth + 1, max_depth, budget, out)
        except Exception:
            return

    def window_title(self) -> str:
        return self._last_window_title

    # ── 操作 ──

    def act(self, element_id: str, action: str = "click", text: Optional[str] = None) -> dict:
        """对指定元素执行动作。返回含 via 标记的结果。

        action: click | double_click | type
        """
        ctrl = self._last_controls.get(element_id)
        if ctrl is None:
            return {"success": False, "error": f"uia element '{element_id}' not found", "via": None}

        if action == "click":
            return self._act_click(ctrl, element_id)
        if action == "double_click":
            return self._act_coord(ctrl, element_id, clicks=2)
        if action == "type":
            return self._act_type(ctrl, element_id, text or "")
        return {"success": False, "error": f"unsupported uia action: {action}", "via": None}

    def _act_click(self, ctrl, element_id: str) -> dict:
        # 1) Invoke —— 最确定
        try:
            ip = ctrl.GetInvokePattern()
            if ip is not None:
                ip.Invoke()
                return {"success": True, "via": "uia_invoke", "element": element_id}
        except Exception:
            pass
        # 2) SelectionItem（列表/菜单项）
        try:
            sp = ctrl.GetSelectionItemPattern()
            if sp is not None:
                sp.Select()
                return {"success": True, "via": "uia_select", "element": element_id}
        except Exception:
            pass
        # 3) Toggle（复选框）
        try:
            tp = ctrl.GetTogglePattern()
            if tp is not None:
                tp.Toggle()
                return {"success": True, "via": "uia_toggle", "element": element_id}
        except Exception:
            pass
        # 4) 坐标回退（UIA bbox 中心，比 OmniParser 框更准）
        return self._act_coord(ctrl, element_id, clicks=1)

    def _act_type(self, ctrl, element_id: str, text: str) -> dict:
        # 1) ValuePattern.SetValue —— 精确设置
        try:
            vp = ctrl.GetValuePattern()
            if vp is not None:
                vp.SetValue(text)
                return {"success": True, "via": "uia_setvalue", "element": element_id}
        except Exception:
            pass
        # 2) 焦点 + 剪贴板粘贴（富文本/无 ValuePattern 的输入框）
        try:
            ctrl.SetFocus()
        except Exception:
            pass
        try:
            from server.services.executor.clicker import type_text

            type_text(text)
            return {"success": True, "via": "coord_clipboard", "element": element_id}
        except Exception as exc:
            return {"success": False, "error": f"type failed: {exc}", "via": None}

    def _act_coord(self, ctrl, element_id: str, clicks: int = 1) -> dict:
        bbox = _control_bbox(ctrl)
        if bbox is None:
            return {"success": False, "error": "uia element has no bbox", "via": None}
        cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
        try:
            from server.services.executor.clicker import click_at

            r = click_at((cx, cy), clicks=clicks)
            return {
                "success": True,
                "via": "coord",
                "element": element_id,
                "x": cx,
                "y": cy,
                "clicks": clicks,
                "detail": r,
            }
        except Exception as exc:
            return {"success": False, "error": f"coord click failed: {exc}", "via": None}

    # ── 校验 ──

    def verify(self, element_id: str, timeout: float = 3.0) -> dict:
        """执行后校验：控件存在、已启用、未离屏（带轮询）。"""
        deadline = time.time() + timeout
        ctrl = self._last_controls.get(element_id)
        if ctrl is None:
            return {"success": False, "reason": "element gone from last snapshot"}
        while time.time() < deadline:
            try:
                if not bool(ctrl.IsEnabled):
                    time.sleep(0.3)
                    continue
                if bool(ctrl.IsOffscreen):
                    time.sleep(0.3)
                    continue
                return {"success": True, "reason": "control enabled & onscreen"}
            except Exception:
                time.sleep(0.3)
        return {"success": False, "reason": "control not ready (disabled/offscreen)"}

    def clear(self) -> None:
        self._last_controls = {}
