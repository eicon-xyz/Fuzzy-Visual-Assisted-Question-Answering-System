"""执行层接管许可（Phase 1）。

设计支点
--------
档位不是工具的属性，是**运行期所走路径的属性**。所以许可门落在「降级边界」上，
而不是落在工具入口上：

    click      UIA Invoke/Select/Toggle  ──失败──▶ 坐标点击（要 POINTER）
    type       ValuePattern.SetValue     ──缺失──▶ 焦点+剪贴板（要 KEYBOARD+CLIPBOARD）
    launch_app subprocess.Popen（层 1/2）──失败──▶ Win+搜索（要 KEYBOARD+CLIPBOARD+ACTIVATE）
    observe    PrintWindow(hwnd)         ──全黑──▶ 整屏 mss（要 FULLSCREEN_GRAB）

把门设在工具入口上的后果是：90% 的正常路径也变成"要授权"。

不变量
------
I1  进程内只有 ``hid.py`` 能 import pyautogui / pydirectinput / pyperclip
    （``tests/test_phase1_hid_boundary.py`` 用 AST 强制）
I2  许可只能由 ``PermitBroker.resolve()`` 签发；令牌种子 ``_MINT`` 不进 ``__all__``
I3  没有许可时 ``hid.*`` 返回 ``permit_required``，绝不静默换路（fail-closed）
I4  坐标系：投影 bbox 一律窗口相对；``hid.*`` 一律屏幕绝对，无隐式换算
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Literal, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ForegroundAction",
    "ForegroundPermit",
    "PermitBroker",
    "PermitState",
    "Refusal",
    "TaskPolicy",
    "derive_policy",
]


class ForegroundAction(str, Enum):
    """一次动作会侵占的桌面资源。按域授权，不做布尔授权。"""

    POINTER = "pointer"        # 光标被搬走
    KEYBOARD = "keyboard"      # 按键落到非本任务窗口
    CLIPBOARD = "clipboard"    # 全局剪贴板被改写（并还原）
    ACTIVATE = "activate"      # 前台窗口被切换 / 控件被 SetFocus
    FULLSCREEN_GRAB = "fullscreen_grab"  # 抓整屏像素（会看到窗口之外的东西）
    WINDOW_MESSAGE = "window_message"    # 向别的进程窗口投递输入消息（不搬光标）


_MINT = object()  # 唯一种子；不进 __all__


class ForegroundPermit:
    """带域的一次性接管令牌。

    Python 封不住构造器（有决心的人照样能 ``__new__``），所以强制手段是三层叠加：
    hid.py 单出口（AST 强制）+ 令牌唯一构造点 + ``hid.*`` 首参无默认值。
    真要 OS 级保证，唯一形状是把 X 档放进独立子进程、主进程只持 IPC 句柄。
    """

    __slots__ = ("actions", "expires_at", "issued_at", "reason", "task_id")

    def __init__(
        self,
        token: object,
        task_id: str,
        actions: Iterable[ForegroundAction],
        ttl_s: float = 1800.0,
        reason: str = "",
    ) -> None:
        if token is not _MINT:
            raise TypeError("ForegroundPermit 只能由 PermitBroker.resolve() 签发")
        self.task_id = task_id
        self.actions = frozenset(actions)
        self.issued_at = time.monotonic()
        self.expires_at = self.issued_at + max(1.0, float(ttl_s))
        self.reason = reason

    @property
    def live(self) -> bool:
        return time.monotonic() < self.expires_at

    def allows(self, action: ForegroundAction) -> bool:
        return self.live and action in self.actions

    def as_list(self) -> list[str]:
        return sorted(a.value for a in self.actions)

    def __repr__(self) -> str:  # 日志用，不含任何密钥
        return (
            f"<ForegroundPermit task={self.task_id} "
            f"actions={self.as_list()} live={self.live}>"
        )


@dataclass(frozen=True)
class TaskPolicy:
    """任务级策略：这个任务**可能需要**侵占哪些桌面资源。

    只是"可能"——真正的拦截发生在降级边界。``exclusive`` 与 ``actions`` 都只描述
    预测，供遥测、前端提示与审计使用；**签发什么域**由 ``PermitBroker.resolve()``
    在任务启动时按 consent 决定（生产路径 ``grant_all=True`` 签发全集），**放不放行**
    由 ``hid._guard`` 在动作前按令牌域判定。三处职责不同，不要互相替代。
    """

    task_id: str
    actions: frozenset[ForegroundAction] = frozenset()
    reasons: tuple[str, ...] = ()
    source: Literal["plan", "debug", "manual"] = "plan"

    @property
    def exclusive(self) -> bool:
        return bool(self.actions)

    def as_dict(self) -> dict:
        return {
            "exclusive": self.exclusive,
            "actions": sorted(a.value for a in self.actions),
            "reasons": list(self.reasons),
            "source": self.source,
        }


@dataclass(frozen=True)
class Refusal:
    """拒绝值。工具层只有这一种拒绝形状，模型只学一种 JSON。"""

    error_code: str
    error: str
    hint: str
    alternatives: tuple[str, ...] = ()
    required_actions: tuple[str, ...] = ()

    def to_tool_result(self) -> dict:
        out = {
            "success": False,
            "action_ok": False,
            "error_code": self.error_code,
            "error": self.error,
            "hint": self.hint,
        }
        if self.alternatives:
            out["alternatives"] = list(self.alternatives)
        if self.required_actions:
            out["required_actions"] = list(self.required_actions)
        return out


class PermitState(str, Enum):
    NOT_REQUESTED = "not_requested"
    GRANTED = "granted"
    DECLINED = "declined"
    REVOKED = "revoked"


# ── 规划期确定性分类 ────────────────────────────────────────────────────────
#
# 不许让 LLM 自己填 exclusive：模型漂移会让同一个任务今天要授权明天不要，
# 授权记录不可审计。这里是纯函数，可单测、可复现。

_VERBS: dict[ForegroundAction, tuple[str, ...]] = {
    ForegroundAction.POINTER: (
        "坐标", "拖", "拖动", "拖拽", "滚动", "滚轮", "右键", "双击",
        "drag", "scroll", "right-click", "right click",
        "double-click", "double click", "move the mouse",
    ),
    ForegroundAction.KEYBOARD: (
        "输入", "键入", "回车", "按键", "快捷键", "热键",
        "type", "press", "hotkey", "keyboard", "enter key",
    ),
    ForegroundAction.CLIPBOARD: (
        "粘贴", "复制", "剪贴板", "paste", "clipboard",
    ),
    ForegroundAction.ACTIVATE: (
        "打开", "启动", "运行", "切换", "激活", "前置", "前台",
        "最小化", "最大化",
        "open", "launch", "start the", "activate",
        "switch", "minimize", "maximize", "bring to front",
    ),
    ForegroundAction.FULLSCREEN_GRAB: (
        "截图", "全屏", "整屏", "screenshot", "fullscreen", "full screen",
    ),
    # 没有"计划里会说 WindowMessage"的动词——它是实现档位，不是用户意图。
    # 由 derive_policy 从 POINTER/KEYBOARD 隐含派生（见下）。
    ForegroundAction.WINDOW_MESSAGE: (),
}


def _iter_instructions(steps: Iterable[dict]) -> Iterable[str]:
    for s in steps or ():
        if not isinstance(s, dict):
            continue
        for key in ("instruction", "goal", "text", "action"):
            val = s.get(key)
            if isinstance(val, str) and val:
                yield val


def derive_policy(task_id: str, goal: str, steps: list[dict]) -> TaskPolicy:
    """从目标与步骤文本派生策略。确定性、无副作用、不调 LLM。

    ``exclusive=True`` 只表示"这个任务可能落到某条降级边界"，不表示用户已被打扰。
    """
    haystack = " ".join([goal or "", *_iter_instructions(steps)]).lower()
    if not haystack.strip():
        return TaskPolicy(task_id=task_id)

    actions: set[ForegroundAction] = set()
    reasons: list[str] = []
    for action in ForegroundAction:
        hit = next((v for v in _VERBS[action] if v.lower() in haystack), None)
        if hit:
            actions.add(action)
            reasons.append(f"{action.value}←«{hit}»")

    # 消息投递是"操作该控件"的严格子集：允许搬光标/发按键，就允许给它发窗口消息
    # （不搬光标、不抢焦点，侵入性更低）。反过来不成立——只允许发消息≠允许搬光标。
    # 不这么派生的话，W 档永远拿不到许可，系统会退回"每次都搬光标"，比现状更差。
    implied = actions & {ForegroundAction.POINTER, ForegroundAction.KEYBOARD}
    if implied and ForegroundAction.WINDOW_MESSAGE not in actions:
        actions.add(ForegroundAction.WINDOW_MESSAGE)
        reasons.append(
            "window_message←隐含于:"
            + "+".join(sorted(a.value for a in implied))
        )

    return TaskPolicy(
        task_id=task_id,
        actions=frozenset(actions),
        reasons=tuple(reasons),
    )


class PermitBroker:
    """进程内、按 task_id 隔离的签发/撤销中心。"""

    def __init__(self) -> None:
        self._permits: dict[str, ForegroundPermit] = {}
        self._states: dict[str, PermitState] = {}
        self._lock = threading.Lock()

    def state(self, task_id: str) -> PermitState:
        with self._lock:
            return self._states.get(task_id, PermitState.NOT_REQUESTED)

    def resolve(
        self,
        policy: TaskPolicy,
        *,
        consent: bool,
        ttl_s: float = 1800.0,
        grant_all: bool = False,
    ) -> Optional[ForegroundPermit]:
        """按策略签发。

        - ``exclusive=False`` → 直接 None，**不询问用户**（不诱导扩大授权）
        - ``exclusive=True`` 且 ``consent`` → 签发；``grant_all=True`` 时签发全集
        - ``exclusive=True`` 且无 consent → None，记 DECLINED（动作会被拒，可改道 UIA）

        ``grant_all`` 的语义：``consent`` 是用户给出的**范围**，``policy.actions``
        只是"会用到哪些域"的**预测**。预测偏窄不会减少打扰，只会让降级边界在
        真正需要时被拒（例："打开某冷门应用"只派生出 activate，而 launch 层 3
        要 keyboard+clipboard+activate），所以生产路径在 consent 到手后按全集
        签发，预测域仅留作遥测与审计。默认 False 保持按域签发，per-domain 机制
        仍是唯一的放行判据（``hid._guard``）。
        """
        with self._lock:
            if not policy.exclusive:
                self._states[policy.task_id] = PermitState.NOT_REQUESTED
                return None
            if not consent:
                self._states[policy.task_id] = PermitState.DECLINED
                logger.info(
                    "[permit] declined task=%s actions=%s",
                    policy.task_id,
                    sorted(a.value for a in policy.actions),
                )
                return None
            granted = (
                frozenset(ForegroundAction) if grant_all else policy.actions
            )
            permit = ForegroundPermit(
                _MINT,
                policy.task_id,
                granted,
                ttl_s=ttl_s,
                reason="; ".join(policy.reasons),
            )
            self._permits[policy.task_id] = permit
            self._states[policy.task_id] = PermitState.GRANTED
            logger.info(
                "[permit] granted task=%s actions=%s reasons=%s",
                policy.task_id,
                permit.as_list(),
                permit.reason,
            )
            return permit

    def get(self, task_id: str) -> Optional[ForegroundPermit]:
        with self._lock:
            return self._permits.get(task_id)

    def revoke(self, task_id: str, reason: str = "task_end") -> None:
        with self._lock:
            permit = self._permits.pop(task_id, None)
            if permit is not None:
                # 令牌已发出去，只能把内部记录作废：hid._guard 读 live/actions，
                # 这里把 actions 清空 + expires_at 置过去时间，等价于立即失效。
                permit.actions = frozenset()
                permit.expires_at = 0.0
                permit.reason = reason
            self._states[task_id] = PermitState.REVOKED


BROKER = PermitBroker()
