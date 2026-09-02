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
        """遍历前台窗口 UIA 树，返回 UIElement 列表（含空间/模式信息）。

        注意：会重置 _last_controls 并重新编号 element_id（旧 id 全部失效）。
        """
        self._last_controls = {}
        return self._snapshot_into(self._last_controls, max_depth, max_nodes)

    def _snapshot_into(
        self,
        store: Dict[str, object],
        max_depth: int = None,
        max_nodes: int = None,
    ) -> List[UIElement]:
        """遍历前台窗口 UIA 树，控件写入给定 store（不传则不动 _last_controls）。

        供 wait_for_text 等「只读轮询」使用：临时 store 保证主快照的
        element_id → 控件映射不被打乱。
        """
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
            self._walk(fg, 0, depth, budget, out, store)
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
        store: Optional[Dict[str, object]] = None,
    ) -> None:
        if depth > max_depth or budget[0] <= 0:
            return
        if store is None:
            store = self._last_controls
        budget[0] -= 1
        try:
            bbox = _control_bbox(control)
            if bbox is not None:
                name = (control.Name or "").strip()
                ctrl_type = _control_type(control)
                # 只保留有名字或可交互的控件，减少噪音
                if name or ctrl_type in ("button", "input", "checkbox", "dropdown", "link"):
                    cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
                    eid = f"u{len(store) + 1}"
                    try:
                        enabled = bool(control.IsEnabled)
                    except Exception:
                        enabled = True
                    patterns = _available_patterns(control)
                    store[eid] = control
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
                self._walk(child, depth + 1, max_depth, budget, out, store)
        except Exception:
            return

    def window_title(self) -> str:
        return self._last_window_title

    # ── 操作 ──

    @staticmethod
    def _props(ctrl) -> Dict[str, object]:
        """采集控件的可观测属性（动作前后 diff 用）。读取失败的键跳过。"""
        props: Dict[str, object] = {}
        try:
            props["name"] = (ctrl.Name or "").strip()
        except Exception:
            pass
        try:
            props["enabled"] = bool(ctrl.IsEnabled)
        except Exception:
            pass
        try:
            props["offscreen"] = bool(ctrl.IsOffscreen)
        except Exception:
            pass
        bbox = _control_bbox(ctrl)
        if bbox is not None:
            props["bbox"] = bbox
        try:
            ecp = ctrl.GetExpandCollapsePattern()
            if ecp is not None:
                props["expand"] = str(getattr(ecp, "ExpandCollapseState", ""))
        except Exception:
            pass
        try:
            vp = ctrl.GetValuePattern()
            if vp is not None:
                val = vp.Value or ""
                # 截断长文本，diff 只需前缀区分
                props["value"] = val[:80]
        except Exception:
            pass
        try:
            sp = ctrl.GetSelectionItemPattern()
            if sp is not None:
                props["selected"] = bool(sp.IsSelected)
        except Exception:
            pass
        return props

    @staticmethod
    def _prop_diff(before: dict, after: dict) -> dict:
        """属性差异：changed 列出变化键，before/after 只保留变化键的值。"""
        keys = set(before) | set(after)
        changed = [k for k in sorted(keys) if before.get(k) != after.get(k)]
        return {
            "changed": changed,
            "before": {k: before.get(k) for k in changed},
            "after": {k: after.get(k) for k in changed},
        }

    def wait_for_text(
        self,
        text: str,
        timeout: float = 3.0,
        interval: float = 0.4,
    ) -> dict:
        """在一次调用内轮询界面，等待包含 text 的控件/窗口标题出现。

        Windows-MCP WaitFor 语义：动作后置条件断言。用独立临时快照轮询，
        不触碰 _last_controls（当前 element_id 映射保持有效）。
        """
        if not self._available or not text:
            return {"ok": False, "reason": "uia unavailable or empty expect"}
        needle = text.strip().lower()
        deadline = time.time() + timeout
        last_title = ""
        while True:
            tmp: Dict[str, object] = {}
            try:
                elements = self._snapshot_into(tmp, max_nodes=120)
            except Exception:
                elements = []
            last_title = self._last_window_title or ""
            if needle in last_title.lower():
                return {"ok": True, "matched": "window_title", "window_title": last_title}
            for el in elements:
                if needle in (el.text or "").lower():
                    return {
                        "ok": True,
                        "matched": el.text,
                        "matched_type": el.element_type,
                        "window_title": last_title,
                    }
            if time.time() >= deadline:
                break
            time.sleep(interval)
        return {
            "ok": False,
            "reason": f"no control/window containing '{text}' within {timeout:.1f}s",
            "window_title": last_title,
        }

    def act(
        self,
        element_id: str,
        action: str = "click",
        text: Optional[str] = None,
        expect: Optional[str] = None,
        verify_timeout: float = 3.0,
        expect_timeout: float = 4.0,
    ) -> dict:
        """对指定元素执行动作，并接线执行后校验。

        返回统一附加字段（0.2 动作后验证）：
          action_ok    —— 动作本身是否送达执行
          verified     —— verify()（enabled/onscreen 轮询）是否通过
          state_changed—— 控件可观测属性（name/enabled/bbox/expand/value/selected）是否变化
          prop_diff    —— before/after 属性差异
          expect_ok    —— 期望条件（wait_for_text）是否满足；未提供 expect 时为 None
        """
        ctrl = self._last_controls.get(element_id)
        if ctrl is None:
            return {
                "success": False,
                "error": f"uia element '{element_id}' not found",
                "via": None,
                "action_ok": False,
            }

        before = self._props(ctrl)

        if action == "click":
            r = self._act_click(ctrl, element_id)
        elif action == "double_click":
            r = self._act_coord(ctrl, element_id, clicks=2)
        elif action == "type":
            r = self._act_type(ctrl, element_id, text or "")
        else:
            return {
                "success": False,
                "error": f"unsupported uia action: {action}",
                "via": None,
                "action_ok": False,
            }

        if not r.get("success"):
            r["action_ok"] = False
            return r

        # ── 动作后验证链（0.2）：控件状态校验 + 属性 diff + 期望条件轮询 ──
        action_ok = True
        r["action_ok"] = action_ok

        v = self.verify(element_id, timeout=verify_timeout)
        r["verified"] = bool(v.get("success"))
        r["verify_reason"] = v.get("reason", "")

        after = self._props(ctrl)
        diff = self._prop_diff(before, after)
        r["state_changed"] = bool(diff["changed"])
        r["prop_diff"] = diff

        if expect:
            w = self.wait_for_text(expect, timeout=expect_timeout)
            r["expect_ok"] = bool(w.get("ok"))
            r["expect_detail"] = w
        else:
            r["expect_ok"] = None

        return r

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
