"""UIA 绑定桥 —— Windows UI Automation 结构化采集 + 精确操作。

背景：原依赖远程 OmniParser GPU(:9800) 做屏幕元素感知，已不可用。
本模块让执行 agent 的「屏幕感知 + 操作」改为：
  1. snapshot(): 遍历前台窗口 UIA 控件树 → HAJIMI UIElement 列表
     （name / control_type / bbox / 可用交互模式 / enabled）
  2. act(): 交互模式由「控件类型决策表 + 快照期缓存探测结果」选定（B2），
     执行失败 fail-closed 报 pattern_failed 停止，不再自动降级下一模式/坐标；
     像素坐标点击仅当调用方显式声明 via="coordinate" 才走
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

import hashlib
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
        ("rangevalue", "GetRangeValuePattern"),  # B4: 滑杆/数值调节
        ("window", "GetWindowPattern"),  # B4: 窗口级动作能力
    ):
        try:
            if getattr(control, getter)() is not None:
                out.append(pname)
        except Exception:
            pass
    return out


# ═══════════════════════════════════════════════════════════════════════════
# B2 点击交互模式决策表（控件语义 → 候选模式，按序取"缓存探测支持"的第一个）
# ═══════════════════════════════════════════════════════════════════════════
# 动词由控件类型语义决定（而非运行时试探链的顺序）。空列表 = 该类型无默认
# 点击语义（输入框用 type_text，纯文本用显式坐标）。keys 是 _raw_control_type
# 归一化后的 ControlTypeName（'ButtonControl'→'button'）。
_CLICK_PATTERN_TABLE = {
    "button": ["invoke"],
    "hyperlink": ["invoke"],
    "checkbox": ["toggle", "invoke"],
    "tabitem": ["selectionitem", "invoke"],
    "listitem": ["selectionitem", "invoke"],
    "treeitem": ["selectionitem", "expandcollapse", "invoke"],
    "menuitem": ["expandcollapse", "invoke", "selectionitem"],
    "combobox": ["expandcollapse", "selectionitem"],
    "edit": [],
    "document": [],  # 点击输入框/文档无默认语义：type_text 或显式坐标
}

# 表外类型（pane/unknown 等）的兜底候选
_DEFAULT_CANDIDATES = ["invoke", "toggle", "selectionitem", "expandcollapse"]


# UFO 同款高价值 ControlType 白名单（10 类）：这些类型的控件无条件保留，
# 替代旧「有名字就要」造成的列表爆炸与关键无名按钮丢失。
_WHITELIST_CONTROL_TYPES = {
    "button",
    "edit",
    "tabitem",
    "document",
    "listitem",
    "menuitem",
    "treeitem",
    "combobox",
    "hyperlink",
    "scrollbar",
}


def _raw_control_type(control) -> str:
    """归一化 ControlTypeName：'ButtonControl' → 'button'。"""
    try:
        name = (getattr(control, "ControlTypeName", "") or "").lower()
    except Exception:
        name = ""
    if name.endswith("control"):
        name = name[: -len("control")]
    return name


# ═══════════════════════════════════════════════════════════════════════════
# 桥接器
# ═══════════════════════════════════════════════════════════════════════════


class UIABridge:
    """UIA 采集 + 操作 + 校验。每个 ExecutionAgent 一个实例。"""

    _MAX_DEPTH = 6
    _MAX_NODES = 120
    # A4: 句柄表容量上限，超限按"最久未被观察"淘汰（FIFO）
    _HANDLE_CAP = 400

    def __init__(self) -> None:
        # ── 当次视图（每次 snapshot 重建，drill 增量）──
        self._last_controls: Dict[str, object] = {}
        self._last_meta: Dict[str, dict] = {}  # B2: {eid: {type, patterns}} 快照期缓存
        self._last_projection: List[dict] = []
        self._last_window_title: str = ""
        self._last_window_rect: Optional[List[int]] = None
        self._last_focused: Optional[dict] = None  # B3: 快照时焦点控件 {name,type,class,bbox}
        # ── A4: 跨快照存活的持久句柄表（clear() 才全清）──
        self._handles: Dict[str, object] = {}  # eid → UIA control（act/verify 消费）
        self._ui_cache: Dict[str, UIElement] = {}  # eid → 最近一次观察的 UIElement 投影
        self._fallback_seq = 0  # 烂控件回退 u{n} 计数（桥实例内单调，防旧号段鬼魂复用）
        self._outline_seq = 0  # A3：大纲临时 id o{n} 计数（不进句柄表）
        self._proj_seq = 0  # 投影 seq 计数器（快照重置、drill 续编）
        self._last_drill_info: dict = {}  # A3/A2：最近一次 drill 根信息
        self._auto = _import_auto()
        self._available = self._auto is not None and platform.system() == "Windows"
        if not self._available:
            _log().info("UIA bridge unavailable (non-Windows or no uiautomation)")

    @property
    def available(self) -> bool:
        return self._available

    # ── 采集 ──

    def snapshot(self, max_depth: int = 3, max_nodes: int = 160) -> List[UIElement]:
        """遍历前台窗口 UIA 树，返回 UIElement 列表（含空间/模式信息）。

        A3 浅探默认：max_depth=3 / max_nodes=160——默认观察比旧值（6/120）更
        便宜，被深度预算挡住未展开的容器产"大纲条目"（items 计数 +
        expandable，见 _emit_outline），深扫交给 drill(scope)。

        A4 稳定 id：eid 由 GetRuntimeId(+hwnd/ProcessId) 派生，句柄表
        （_handles/_ui_cache）跨快照存活——观察不再使旧 id 作废，控件销毁
        后由 act/verify 报 element_stale。会重置的只是"当次视图"
        （_last_controls/_last_projection/_last_meta/_last_focused），
        刷新为本次观察到的控件视图。_last_projection 为 0.1 感知序列化
        （type/name/class/enabled/patterns/窗口相对 bbox/seq），_last_meta
        为 B2 决策表缓存。
        """
        self._last_controls = {}
        self._last_meta = {}
        self._last_projection = []
        self._last_focused = None
        self._proj_seq = 0
        out = self._snapshot_into(self._last_controls, max_depth, max_nodes)
        # B3: 快照成功后记录当前焦点控件（供 agent 观察结果头部附 focused 字段）
        if self._available:
            self._last_focused = self._capture_focused()
        return out

    def _capture_focused(self) -> Optional[dict]:
        """GetFocusedControl() 属性采集（B3）。模块无此函数/取不到 → None。

        逐字段 try/except；bbox 为绝对坐标（与投影相对坐标区分）。
        不在任何缓存字段落盘——last_focused() 只是读本方法的结果快照。
        """
        if not self._available or self._auto is None:
            return None
        getter = getattr(self._auto, "GetFocusedControl", None)
        if not callable(getter):
            return None
        try:
            ctrl = getter()
        except Exception:
            return None
        if ctrl is None:
            return None
        out: dict = {}
        try:
            out["name"] = (ctrl.Name or "").strip()
        except Exception:
            out["name"] = ""
        try:
            out["type"] = _raw_control_type(ctrl) or "pane"
        except Exception:
            out["type"] = ""
        try:
            out["class"] = (ctrl.ClassName or "").strip()
        except Exception:
            out["class"] = ""
        bbox = _control_bbox(ctrl)
        if bbox is not None:
            out["bbox"] = bbox  # 绝对坐标
        return out

    def last_focused(self) -> Optional[dict]:
        """最近一次 snapshot() 时捕获的焦点控件属性（无则 None）。"""
        return self._last_focused

    def get_focused_now(self) -> Optional[dict]:
        """动作时刻重取当前焦点控件属性；不落任何缓存字段。"""
        return self._capture_focused()

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
            win_rect = _control_bbox(fg)
            if store is self._last_controls:
                self._last_window_rect = win_rect
            self._walk(fg, 0, depth, budget, out, store, win_rect)
        except Exception as exc:
            _log().debug("UIA snapshot failed: %s", exc)
        return out

    def last_projection(self) -> List[dict]:
        """最近一次 snapshot() 的投影字段列表（0.1 感知序列化）。"""
        return self._last_projection

    # ── A4 稳定 id / 持久句柄 ──

    @staticmethod
    def _stable_base_eid(control) -> Optional[str]:
        """eid = 'e' + sha1(hwnd|'/' + runtime-id)[:10]。

        hwnd 前缀尽力取 ProcessId → 顶层窗口 NativeWindowHandle（都取不到
        用空串，runtime-id 本身在 UIA 会话内已唯一）。GetRuntimeId 缺失/
        异常/空 → None（调用方回退现场序 u{n}，兼容烂控件）。
        """
        try:
            rid = control.GetRuntimeId()
            if rid is None:
                return None
            rid_part = "|".join(str(x) for x in rid)
        except Exception:
            return None
        if not rid_part:
            return None
        hwnd = ""
        try:
            pid = getattr(control, "ProcessId", None)
            if pid is not None:
                hwnd = str(pid)
        except Exception:
            pass
        if not hwnd:
            try:
                top = control.GetTopLevelControl()
                h = getattr(top, "NativeWindowHandle", None)
                if h is not None:
                    hwnd = str(h)
            except Exception:
                pass
        try:
            key = ((hwnd or "") + "/" + rid_part).encode("utf-8", "replace")
            return "e" + hashlib.sha1(key).hexdigest()[:10]
        except Exception:
            return None

    def _assign_eid(self, control, view: Dict[str, object]) -> str:
        """为控件定 eid（A4）。

        - 可解析 runtime-id → 稳定 e<hash>；同一次观察内撞号（不同控件算出
          同一 base）→ 追加 #2 序号；跨观察同 base = 同一控件，原地刷新句柄。
        - 不可解析 → 回退现场序 u{n}，桥实例内单调递增不回头（防旧 id 被
          重建控件"鬼魂"解析——台账 A4 反鬼魂协议）。
        """
        base = self._stable_base_eid(control)
        if base is None:
            self._fallback_seq += 1
            return f"u{self._fallback_seq}"
        eid = base
        k = 2
        while eid in view:  # 仅当次观察占用才算冲突（句柄表里旧条目=同控件，直接覆盖）
            eid = f"{base}#{k}"
            k += 1
        return eid

    def _register_handle(self, eid: str, control, ui: Optional[UIElement] = None) -> None:
        """句柄/投影缓存登记（A4，跨快照存活）。超容量按最久未观察淘汰。

        A3：大纲容器的稳定 id 也登记句柄（drill 可达），但不带 UIElement
        （不进 _ui_cache → agent 端不可 act——防"对折叠容器开枪"）。
        """
        if eid in self._handles:
            self._handles.pop(eid)
        self._handles[eid] = control
        if ui is not None:
            if eid in self._ui_cache:
                self._ui_cache.pop(eid)
            self._ui_cache[eid] = ui
        while len(self._handles) > self._HANDLE_CAP:
            oldest = next(iter(self._handles))
            self._handles.pop(oldest, None)
            self._ui_cache.pop(oldest, None)

    @staticmethod
    def _control_alive(ctrl) -> bool:
        """存活探针：已销毁控件读廉价属性即抛（COMError/ElementNotAvailable）。"""
        try:
            _ = ctrl.Name
            return True
        except Exception:
            return False

    def has_handle(self, element_id: str) -> bool:
        """A4：句柄表里是否有该 eid（跨快照存活判据）。"""
        return element_id in self._handles

    def scope_status(self, element_id: str) -> str:
        """A3：scope 下钻前置探测——'live'（可 drill）/'stale'（句柄已死）/'unknown'。"""
        ctrl = self._handles.get(element_id)
        if ctrl is None:
            return "unknown"
        if not self._control_alive(ctrl):
            return "stale"
        return "live"

    def ui_cache(self) -> Dict[str, UIElement]:
        """A4：eid → 最近观察 UIElement 的跨快照缓存（agent element_map 直用）。"""
        return self._ui_cache

    # ── A3 按需下钻（drill = 加法，不重置既有映射）──

    def drill(
        self,
        element_id: str,
        max_depth: int = 6,
        max_nodes: int = 80,
    ) -> List[UIElement]:
        """从 _handles[element_id] 出发子树深扫 + pattern 探测（A3）。

        增量写入 _last_controls/_last_meta/_last_projection/_handles（不重置
        既有映射——drill 是加法，其余 id 不失效）；子树内被再次观察的 id 的
        投影条目按新结果替换。不可解析/句柄已死 → 返回 []（调用方先用
        scope_status 区分错误语义）。返回子树 UIElement 列表（含子树自身的
        浅探大纲条目，若子树仍超深）。
        """
        if not self._available:
            return []
        ctrl = self._handles.get(element_id)
        if ctrl is None or not self._control_alive(ctrl):
            return []
        budget = [max(1, int(max_nodes or 80))]
        depth = max(1, int(max_depth or 6))
        out: List[UIElement] = []
        root_type = _raw_control_type(ctrl)
        root_rect = _control_bbox(ctrl)
        win_rect = self._last_window_rect
        if root_type == "window" and root_rect:
            # A2 铺垫：scope 指向顶层窗口 → 观察基准换成该窗（切焦点观察）
            win_rect = root_rect
            self._last_window_rect = root_rect
            try:
                self._last_window_title = (ctrl.Name or "").strip()
            except Exception:
                pass
        before = len(self._last_projection)
        self._walk(ctrl, 0, depth, budget, out, self._last_controls, win_rect)
        new_entries = self._last_projection[before:]
        new_ids = {p["id"] for p in new_entries}
        new_objs = {id(p) for p in new_entries}
        self._last_projection = [
            p for p in self._last_projection
            if id(p) in new_objs or p.get("id") not in new_ids
        ]
        try:
            root_name = (ctrl.Name or "").strip()
        except Exception:
            root_name = ""
        self._last_drill_info = {
            "scope": element_id,
            "root_type": root_type,
            "title": root_name if root_type == "window" else "",
            # 本次 drill 写入/刷新的全部投影 id（含子树内新生成的浅探大纲条目）
            "ids": set(new_ids),
        }
        return out

    def last_drill_info(self) -> dict:
        """最近一次 drill 的根信息（A2：observing_window 用）。"""
        return getattr(self, "_last_drill_info", {}) or {}

    def _emit_outline(
        self,
        control,
        children: List[object],
        bbox: Optional[List[int]],
        win_rect: Optional[List[int]],
        existing_entry: Optional[dict],
    ) -> None:
        """A3 大纲条目：被深度预算挡住未展开的容器（仍有 children 且
        d==max_depth）也要"被看见"。只数 children 不做 pattern 探测（成本红线）。

        - 容器本身已在投影里（白名单类型等）→ 原地补 items/expandable 字段；
        - 否则产独立条目：id 可解析 runtime-id → 稳定 eid（进句柄表可 drill，
          不进 ui_cache 不可 act）；不可解析 → 临时 "o{n}"（不进句柄表，
          drill/act 都不接受——agent 端按 o 前缀直接给"先整窗观察"hint）。
        """
        n = len(children)
        items = n if n <= 200 else "200+"
        if existing_entry is not None:
            existing_entry["items"] = items
            existing_entry["expandable"] = True
            return
        if bbox is None:
            return  # 不可见容器不进大纲
        eid = self._stable_base_eid(control)
        if eid is None or eid in self._last_controls or eid in {
            p.get("id") for p in self._last_projection
        }:
            self._outline_seq += 1
            eid = f"o{self._outline_seq}"
        else:
            self._register_handle(eid, control)
        try:
            name = (control.Name or "").strip()
        except Exception:
            name = ""
        rel = bbox
        if win_rect:
            rel = [
                bbox[0] - win_rect[0],
                bbox[1] - win_rect[1],
                bbox[2] - bbox[0],
                bbox[3] - bbox[1],
            ]
        self._last_projection.append(
            {
                "id": eid,
                "type": _raw_control_type(control) or "pane",
                "name": name,
                "class": "",
                "enabled": True,
                "patterns": [],
                "bbox": rel,
                "seq": self._proj_seq,
                "items": items,
                "expandable": True,
            }
        )
        self._proj_seq += 1

    def _walk(
        self,
        control,
        depth: int,
        max_depth: int,
        budget: List[int],
        out: List[UIElement],
        store: Optional[Dict[str, object]] = None,
        win_rect: Optional[List[int]] = None,
    ) -> None:
        if depth > max_depth or budget[0] <= 0:
            return
        if store is None:
            store = self._last_controls
        budget[0] -= 1
        try:
            bbox = _control_bbox(control)
            entry_for_outline: Optional[dict] = None  # A3：本节点已发的投影条目
            if bbox is not None:
                name = (control.Name or "").strip()
                raw_type = _raw_control_type(control)
                patterns = _available_patterns(control)
                interactive = bool(patterns)
                # 两级过滤（UFO 式硬过滤）：白名单 ControlType 无条件保留；
                # 其余仅保留「有名字且可交互」的控件，压掉布局噪声。
                keep = raw_type in _WHITELIST_CONTROL_TYPES or (name and interactive)
                if keep:
                    ctrl_type = _control_type(control)
                    cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
                    eid = self._assign_eid(control, store)  # A4 稳定 id
                    try:
                        enabled = bool(control.IsEnabled)
                    except Exception:
                        enabled = True
                    store[eid] = control
                    ui = UIElement(
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
                    out.append(ui)
                    if store is self._last_controls:
                        # A4: 句柄表跨快照存活（act/verify 消费 _handles）
                        self._register_handle(eid, control, ui)
                        # B2: 决策表缓存——eid → {type(raw), patterns}，act 期零探测
                        self._last_meta[eid] = {"type": raw_type, "patterns": patterns}
                        # 投影字段：bbox 换算为相对前台窗口左上角，
                        # LLM 由此推断左右/上下/行列关系（替代恒空的空间关系死条款）。
                        rel = bbox
                        if win_rect:
                            rel = [
                                bbox[0] - win_rect[0],
                                bbox[1] - win_rect[1],
                                bbox[2] - bbox[0],
                                bbox[3] - bbox[1],
                            ]
                        try:
                            cls = (control.ClassName or "").strip()
                        except Exception:
                            cls = ""
                        # A4: seq=快照（DFS）序。id 不再编码索引后，agent 截断
                        # 重排改消费该字段（旧实现从 id 后缀整数推索引序）。
                        self._last_projection.append(
                            {
                                "id": eid,
                                "type": raw_type or "pane",
                                "name": name,
                                "class": cls,
                                "enabled": enabled,
                                "patterns": patterns,
                                "bbox": rel,  # [左, 上, 宽, 高]（相对窗口，px）
                                "seq": self._proj_seq,
                            }
                        )
                        self._proj_seq += 1
                        entry_for_outline = self._last_projection[-1]
            children = control.GetChildren()
            # A3 浅探大纲：被深度预算挡住未展开的容器（仍有 children 且
            # d==max_depth）暴露"被折叠"的事实——items 计数 + expandable。
            # 复用刚取到的 children，只数不做 pattern 探测（成本红线）。
            if store is self._last_controls and depth == max_depth and children:
                self._emit_outline(control, children, bbox, win_rect, entry_for_outline)
            for child in children:
                if budget[0] <= 0:
                    break
                self._walk(child, depth + 1, max_depth, budget, out, store, win_rect)
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
            # B4: RangeValue（滑杆/数值），set_range 后 state_changed 由此触发
            rvp = ctrl.GetRangeValuePattern()
            if rvp is not None:
                props["range"] = float(rvp.Value)
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

    def _scan_for_text(self, needle: str) -> Optional[dict]:
        """遍历前台窗口 UIA 树（不受投影白名单限制），找 Name 含 needle 的节点。

        expect/WaitFor 常匹配静态文本标签（Text/Custom），它们不进可交互投影，
        因此这里做独立的轻量扫描，命中返回 {name, type}。
        """
        auto = self._auto
        budget = [200]
        try:
            fg = auto.GetForegroundControl()
        except Exception:
            fg = None
        if fg is None:
            return None
        try:
            stack = [(fg, 0)]
        except Exception:
            return None
        while stack and budget[0] > 0:
            node, d = stack.pop()
            budget[0] -= 1
            try:
                node_name = (node.Name or "").strip()
            except Exception:
                node_name = ""
            if node_name and needle in node_name.lower():
                return {"name": node_name, "type": _raw_control_type(node)}
            if d >= 8:
                continue
            try:
                for child in reversed(node.GetChildren()):
                    stack.append((child, d + 1))
            except Exception:
                pass
        return None

    def wait_for_text(
        self,
        text: str,
        timeout: float = 3.0,
        interval: float = 0.4,
    ) -> dict:
        """在一次调用内轮询界面，等待包含 text 的控件/窗口标题出现。

        Windows-MCP WaitFor 语义：动作后置条件断言。独立轻量扫描，
        不触碰 _last_controls（当前 element_id 映射保持有效）。
        """
        if not self._available or not text:
            return {"ok": False, "reason": "uia unavailable or empty expect"}
        needle = text.strip().lower()
        deadline = time.time() + timeout
        last_title = ""
        while True:
            try:
                fg = self._auto.GetForegroundControl()
                last_title = (fg.Name or "") if fg is not None else ""
            except Exception:
                pass
            if needle in last_title.lower():
                return {"ok": True, "matched": "window_title", "window_title": last_title}
            hit = self._scan_for_text(needle)
            if hit is not None:
                hit["ok"] = True
                hit["window_title"] = last_title
                return hit
            if time.time() >= deadline:
                break
            time.sleep(interval)
        return {
            "ok": False,
            "reason": f"no control/window containing '{text}' within {timeout:.1f}s",
            "window_title": last_title,
        }

    def _check_actionable(
        self, ctrl, action: str = "click", timeout: float = 3.0, sample_interval: float = 0.2
    ) -> dict:
        """0.8 Playwright 式 actionability 前置谓词（等待条件，不等待时间）。

        谓词链（映射到 UIA）：
          Visible   → IsOffscreen == False
          Enabled   → IsEnabled == True
          Stable    → 连续两次采样（间隔 sample_interval）bbox 不变（动画停）
          ReceivesEvents → GetClickablePoint 可得且落在 bbox 内（不被遮挡，仅点击类）
        任一谓词不满足时在 timeout 内轮询；超时返回缺失项。
        """
        deadline = time.time() + timeout
        last_bbox: Optional[List[int]] = None
        while True:
            try:
                offscreen = bool(ctrl.IsOffscreen)
            except Exception:
                offscreen = False
            try:
                enabled = bool(ctrl.IsEnabled)
            except Exception:
                enabled = True
            bbox = _control_bbox(ctrl)
            stable = bbox is not None and last_bbox is not None and bbox == last_bbox
            obscured = False
            if action in ("click", "double_click", "right_click"):
                get_cp = getattr(ctrl, "GetClickablePoint", None)
                if callable(get_cp):
                    try:
                        cp = get_cp()
                        if cp is not None and bbox is not None:
                            if not (
                                bbox[0] <= cp[0] <= bbox[2]
                                and bbox[1] <= cp[1] <= bbox[3]
                            ):
                                obscured = True
                    except Exception:
                        obscured = True
            if bbox is not None and not offscreen and enabled and stable and not obscured:
                return {"actionable": True}
            last_bbox = bbox
            if time.time() >= deadline:
                missing = []
                if offscreen:
                    missing.append("visible")
                if not enabled:
                    missing.append("enabled")
                if not stable:
                    missing.append("stable")
                if obscured:
                    missing.append("receives_events")
                if bbox is None:
                    missing.append("bbox")
                return {
                    "actionable": False,
                    "missing": missing,
                    "waited_ms": int(timeout * 1000),
                }
            time.sleep(sample_interval)

    def act(
        self,
        element_id: str,
        action: str = "click",
        text: Optional[str] = None,
        expect: Optional[str] = None,
        verify_timeout: float = 3.0,
        expect_timeout: float = 4.0,
        action_timeout: float = 3.0,
        via: Optional[str] = None,
        value: Optional[float] = None,
    ) -> dict:
        """对指定元素执行动作，并接线执行后校验。

        via: B2 最小逃生舱——仅当 via == "coordinate" 且 action == "click" 时
        跳过决策表选择阶段直走控件 bbox 坐标点击（显式声明才允许）；
        其余动作/取值忽略。actionability 前置预检不受影响照常执行。

        value: B4 set_range 的目标数值（float）。其余动作忽略。

        返回统一附加字段（0.2 动作后验证）：
          action_ok    —— 动作本身是否送达执行
          verified     —— verify()（enabled/onscreen 轮询）是否通过
          state_changed—— 控件可观测属性（name/enabled/bbox/expand/value/range/selected）是否变化
          prop_diff    —— before/after 属性差异
          expect_ok    —— 期望条件（wait_for_text）是否满足；未提供 expect 时为 None
        """
        ctrl = self._handles.get(element_id)  # A4: 消费持久句柄表（跨快照存活）
        if ctrl is None:
            return {
                "success": False,
                "error": f"uia element '{element_id}' not found",
                "via": None,
                "action_ok": False,
            }
        # A4 element_stale 协议（优先级高于 not_actionable/pattern_failed：
        # 先判存活再执行；死控件读属性会抛，绝不能落到坐标点击）。
        if not self._control_alive(ctrl):
            return {
                "success": False,
                "error_code": "element_stale",
                "error": (
                    f"uia element '{element_id}' is stale "
                    "(control destroyed or UI repainted)"
                ),
                "via": None,
                "action_ok": False,
                "hint": (
                    "控件已销毁或界面已重绘，get_screen_info 重新观察后选新 id；"
                    "不要重试旧 id"
                ),
            }

        # 0.8 唯一解析软校验：同名多控件提醒（不阻断，由 agent/LLM 消歧）
        result_meta = {}
        try:
            target_name = (getattr(ctrl, "Name", "") or "").strip()
            if target_name:
                dup = sum(
                    1
                    for p in self._last_projection
                    if p.get("name") == target_name
                )
                if dup > 1:
                    result_meta["ambiguous_same_name"] = dup
        except Exception:
            pass

        # 0.8 actionability 前置谓词链：不满足 → 拒发动作并回报缺失谓词
        chk = self._check_actionable(ctrl, action=action, timeout=action_timeout)
        if not chk.get("actionable"):
            missing = chk.get("missing", [])
            return {
                "success": False,
                "action_ok": False,
                "via": None,
                "error_code": "not_actionable",
                "error": (
                    f"element not actionable: missing={'+'.join(missing)} "
                    f"(waited {chk.get('waited_ms', 0)}ms)"
                ),
                "missing_predicates": missing,
                "hint": (
                    "控件未就绪（" + "/".join(missing) + "）。这是时机或目标问题："
                    "若界面在加载/动画，稍后重试；若元素不可用或被遮挡，"
                    "get_screen_info 换 enabled=true 的同功能控件，勿硬点。"
                ),
                **result_meta,
            }

        before = self._props(ctrl)

        if action == "click":
            if via == "coordinate":
                # B2 最小逃生舱：显式声明坐标点击（自绘/无 pattern 控件）
                r = self._act_coord(ctrl, element_id, clicks=1)
            else:
                r = self._act_click(ctrl, element_id)
        elif action == "double_click":
            r = self._act_coord(ctrl, element_id, clicks=2)
        elif action == "right_click":
            # B4: 右键语义=像素事件（弹系统上下文菜单），不走决策表选模式
            r = self._act_coord(ctrl, element_id, clicks=1, button="right")
        elif action == "set_range":
            r = self._act_set_range(ctrl, element_id, value)
        elif action == "type":
            r = self._act_type(ctrl, element_id, text or "")
        elif action in ("expand", "collapse"):
            r = self._act_expand(ctrl, element_id, expand=(action == "expand"))
        else:
            return {
                "success": False,
                "error": f"unsupported uia action: {action}",
                "via": None,
                "action_ok": False,
            }

        if not r.get("success"):
            r["action_ok"] = False
            r.update(result_meta)
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

        r.update(result_meta)
        return r

    def _act_click(self, ctrl, element_id: str) -> dict:
        """B2 决策表两阶段：零执行选模式（快照缓存探测结果）→ fail-closed 执行。

        - 选择阶段：动词由「控件类型决策表」而非运行时试探链顺序决定；支持性
          用 _last_meta 快照期缓存（缺失时防御性现场只探测一次，不执行）。
        - 执行阶段：选定模式单次执行，任何异常报 pattern_failed 停止——绝不
          再落到下一模式或坐标（双触发/坐标失效风险归零）。
        - 自动坐标回退已移除：无模式返回 action_ambiguous，坐标需显式 via。
        """
        # ── 选择阶段（零执行）──
        meta = self._last_meta.get(element_id, {})
        ctype = meta.get("type")
        cached = meta.get("patterns")
        if cached is None:
            # 快照缓存缺失（无 snapshot / 防御场景）：现场只探测一次，不执行
            cached = _available_patterns(ctrl)
            if ctype is None:
                ctype = _raw_control_type(ctrl)
        candidates = _CLICK_PATTERN_TABLE.get(ctype, _DEFAULT_CANDIDATES)
        pattern = next((c for c in candidates if c in cached), None)
        if pattern is None:
            try:
                name = (ctrl.Name or "").strip()
            except Exception:
                name = ""
            return {
                "success": False,
                "action_ok": False,
                "via": None,
                "error_code": "action_ambiguous",
                "error": f"no interactive pattern for {ctype or 'unknown'} control '{name}'",
                "hint": (
                    "该控件无可用交互模式：输入框改用 type_text；确需像素点击"
                    "（自绘/无pattern控件）显式传 via='coordinate'；或重新观察换目标。"
                ),
            }
        if pattern == "expandcollapse":
            # 菜单头/下拉框：点击=展开，保留"已展开幂等"语义
            r = self._act_expand(ctrl, element_id, expand=True)
            if not r.get("success"):
                r["action_ok"] = False
                r["error_code"] = "pattern_failed"
                r["hint"] = (
                    "模式执行失败（常见：控件在动作瞬间已销毁/应用无响应）。"
                    "禁止重试同一动作补刀——先 get_screen_info 确认界面实际状态"
                    "（动作可能已生效）再决策。"
                )
            return r

        # ── 执行阶段（fail-closed）──
        exec_spec = {
            "invoke": ("GetInvokePattern", "Invoke", "uia_invoke"),
            "selectionitem": ("GetSelectionItemPattern", "Select", "uia_select"),
            "toggle": ("GetTogglePattern", "Toggle", "uia_toggle"),
        }[pattern]
        getter, method, via = exec_spec
        try:
            pat = getattr(ctrl, getter)()
            if pat is None:
                raise RuntimeError("pattern not found")
            getattr(pat, method)()
        except Exception as exc:
            return {
                "success": False,
                "action_ok": False,
                "via": None,
                "error_code": "pattern_failed",
                "error": f"{pattern} exec failed: {exc}",
                "hint": (
                    "模式执行失败（常见：控件在动作瞬间已销毁/应用无响应）。"
                    "禁止重试同一动作补刀——先 get_screen_info 确认界面实际状态"
                    "（动作可能已生效）再决策。"
                ),
            }
        return {
            "success": True,
            "via": via,
            "element": element_id,
            "pattern": pattern,  # 调试/遥测：实际执行的模式名
        }

    def _act_expand(self, ctrl, element_id: str, expand: bool = True) -> dict:
        """显式 ExpandCollapse.Expand()/Collapse()。"""
        try:
            ep = ctrl.GetExpandCollapsePattern()
        except Exception:
            ep = None
        if ep is None:
            return {
                "success": False,
                "error": "element has no ExpandCollapsePattern（它不是菜单/下拉/树节点？改用 click）",
                "via": None,
            }
        try:
            state = str(getattr(ep, "ExpandCollapseState", "") or "")
            if expand:
                # B2: 保留"已展开幂等"——已展开则不再重复 Expand（原 _act_click
                # click→expand 分支语义，决策表转调后仍成立）
                if "expanded" not in state.lower():
                    ep.Expand()
                via = "uia_expand"
            else:
                ep.Collapse()
                via = "uia_collapse"
            return {
                "success": True,
                "via": via,
                "element": element_id,
                "expand_from": state,
            }
        except Exception as exc:
            return {"success": False, "error": f"expand/collapse failed: {exc}", "via": None}

    def _act_type(self, ctrl, element_id: str, text: str) -> dict:
        # B2: 支持性判断走快照缓存（value），不再执行期 GetValuePattern 试探；
        # 缺失时防御性现场只探测一次。value 优先→焦点+剪贴板是既有设计语义。
        meta = self._last_meta.get(element_id, {})
        cached = meta.get("patterns")
        if cached is None:
            cached = _available_patterns(ctrl)
        if "value" in cached:
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

    def _act_set_range(self, ctrl, element_id: str, value) -> dict:
        """B4 set_range：RangeValuePattern.Value = float（滑杆/数值调节）。

        支持性用 _last_meta 快照缓存（B2 probe/exec 分离语义，缓存缺失时
        防御性现场只探测一次）；无 rangevalue → no_range_pattern（未执行），
        执行异常 → pattern_failed fail-closed（同 B2 语义，禁补刀）。
        """
        meta = self._last_meta.get(element_id, {})
        cached = meta.get("patterns")
        if cached is None:
            cached = _available_patterns(ctrl)
        if "rangevalue" not in cached:
            try:
                name = (ctrl.Name or "").strip()
            except Exception:
                name = ""
            return {
                "success": False,
                "action_ok": False,
                "via": None,
                "error_code": "no_range_pattern",
                "error": f"control '{name}' does not support RangeValuePattern",
                "hint": (
                    "该控件不支持 RangeValue；试 press_key 方向键/Home/End "
                    "或重新观察选对控件"
                ),
            }
        try:
            pat = ctrl.GetRangeValuePattern()
            if pat is None:
                raise RuntimeError("pattern not found")
            target = float(value)
            pat.Value = target
        except Exception as exc:
            return {
                "success": False,
                "action_ok": False,
                "via": None,
                "error_code": "pattern_failed",
                "error": f"rangevalue exec failed: {exc}",
                "hint": (
                    "模式执行失败（常见：控件在动作瞬间已销毁/应用无响应）。"
                    "禁止重试同一动作补刀——先 get_screen_info 确认界面实际状态"
                    "（动作可能已生效）再决策。"
                ),
            }
        return {
            "success": True,
            "via": "uia_setrange",
            "element": element_id,
            "pattern": "rangevalue",
            "range_value": target,
        }

    # ── B4 窗口级动作 ──

    _WINDOW_OPS = ("activate", "minimize", "maximize", "restore", "close")
    # 直接方法名（uiautomation Control 原生）→ op
    _WINDOW_DIRECT_METHODS = {
        "minimize": "Minimize",
        "maximize": "Maximize",
        "restore": "Restore",
        "close": "Close",
    }
    # WindowPattern 回退：op → (方法, 参数枚举名 SetWindowVisualState 用)
    _WINDOW_VISUAL_STATE = {"minimize": "Minimized", "maximize": "Maximized", "restore": "Normal"}

    def _find_window_by_title(self, title: str):
        """桌面根窗口子级中按 Name 含 title（小写）找顶层窗口；无匹配 None。"""
        needle = (title or "").strip().lower()
        if not needle or self._auto is None:
            return None
        try:
            root = self._auto.GetRootControl()
            children = root.GetChildren() if root is not None else []
        except Exception:
            return None
        for w in children:
            try:
                nm = w.Name or ""
            except Exception:
                continue
            if needle in nm.lower():
                return w
        return None

    def act_window(self, op: str, title: str = "", element_id: str = "") -> dict:
        """B4 窗口级动作：activate/minimize/maximize/restore/close（fail-closed）。

        目标解析：element_id → GetTopLevelControl()（getattr 缺失/失败回退按
        title）；title → 桌面根窗口子级按 Name 含 title（小写）匹配；无匹配 →
        window_not_found。执行优先 Control 原生方法（Minimize/Maximize/Restore/
        Close/SetFocus），缺失回退 WindowPattern，再缺 → pattern_failed。
        """
        if not self._available:
            return {
                "success": False,
                "via": None,
                "error_code": "window_not_found",
                "error": "uia bridge unavailable",
                "hint": "窗口动作需 Windows+UIA 环境；确认 Sidecar 运行平台上再试。",
            }
        if op not in self._WINDOW_OPS:
            return {
                "success": False,
                "via": None,
                "error_code": "window_not_found",
                "error": f"unsupported window op: {op}",
                "hint": "op 仅支持 activate/minimize/maximize/restore/close。",
            }
        ctrl = None
        if element_id:
            src = self._handles.get(element_id)  # A4: 跨快照句柄
            if src is not None:
                top = getattr(src, "GetTopLevelControl", None)
                if callable(top):
                    try:
                        ctrl = top()
                    except Exception:
                        ctrl = None
        if ctrl is None:
            ctrl = self._find_window_by_title(title)
        if ctrl is None:
            return {
                "success": False,
                "via": None,
                "error_code": "window_not_found",
                "error": f"no window matched title='{title}' (element_id='{element_id or '-'}')",
                "hint": (
                    "找不到目标窗口：先 get_screen_info 看 window_title，传真实"
                    "标题关键词（子串即可）；不要臆造窗口名。"
                ),
            }
        try:
            win_name = (ctrl.Name or "").strip()
        except Exception:
            win_name = ""

        def _fail(exc) -> dict:
            return {
                "success": False,
                "via": None,
                "error_code": "pattern_failed",
                "error": f"window {op} failed: {exc}",
                "hint": (
                    "窗口动作失败且可能部分生效（禁用同参补刀）。press_key 组合键"
                    "（win+方向键/alTab）是一条不同路径，或重新观察确认窗口状态再决策。"
                ),
            }

        try:
            if op == "activate":
                ctrl.SetFocus()
                method = "SetFocus"
            else:
                method = None
                direct = getattr(ctrl, self._WINDOW_DIRECT_METHODS[op], None)
                if callable(direct):
                    direct()
                    method = self._WINDOW_DIRECT_METHODS[op]
                else:
                    # 回退 WindowPattern
                    wp = ctrl.GetWindowPattern()
                    if wp is None:
                        raise RuntimeError("no window method nor WindowPattern")
                    if op == "close":
                        wp.Close()
                    else:
                        vs_cls = getattr(self._auto, "WindowVisualState", None)
                        state = (
                            getattr(vs_cls, self._WINDOW_VISUAL_STATE[op], None)
                            if vs_cls is not None
                            else None
                        )
                        if state is None:
                            raise RuntimeError("no WindowVisualState enum for op")
                        wp.SetWindowVisualState(state)
                    method = "WindowPattern"
        except Exception as exc:
            return _fail(exc)
        return {
            "success": True,
            "via": "uia_window",
            "window_op": op,
            "window_title": win_name,
            "method": method,
            "action_summary": f"window {op} '{win_name or title}'（{method}）",
        }

    def _act_coord(self, ctrl, element_id: str, clicks: int = 1, button: str = "left") -> dict:
        bbox = _control_bbox(ctrl)
        if bbox is None:
            return {"success": False, "error": "uia element has no bbox", "via": None}
        cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
        try:
            from server.services.executor.clicker import click_at

            r = click_at((cx, cy), clicks=clicks, button=button)
            return {
                "success": True,
                "via": "coord",
                "element": element_id,
                "x": cx,
                "y": cy,
                "clicks": clicks,
                "button": button,
                "detail": r,
            }
        except Exception as exc:
            return {"success": False, "error": f"coord click failed: {exc}", "via": None}

    # ── 校验 ──

    def verify(self, element_id: str, timeout: float = 3.0) -> dict:
        """执行后校验：控件存在、已启用、未离屏（带轮询）。A4 走持久句柄表。"""
        deadline = time.time() + timeout
        ctrl = self._handles.get(element_id)
        if ctrl is None:
            return {"success": False, "reason": "element gone from last snapshot"}
        if not self._control_alive(ctrl):  # A4: 控件销毁 → stale，不进轮询
            return {"success": False, "reason": "element stale (control destroyed)"}
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
        """全清（换步语义：agent clear_element_map 调用）。A4 起这是唯一使
        全部 element_id 作废的通道——snapshot 不再作废任何 id。"""
        self._last_controls = {}
        self._last_meta = {}
        self._last_projection = []
        self._last_focused = None
        self._handles = {}
        self._ui_cache = {}
        self._fallback_seq = 0
        self._outline_seq = 0
        self._last_drill_info = {}
