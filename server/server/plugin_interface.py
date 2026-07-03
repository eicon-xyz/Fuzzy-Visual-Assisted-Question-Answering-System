"""
插件抽象接口（参考 OpenGuider plugin-interface.js + plugin-registry.js）

每个插件必须继承 OpenGuiderPlugin 并实现全部抽象方法。
插件由 PluginRegistry 统一管理生命周期。

设计原则：
- 身份属性 (id/name/version/capabilities) 为只读 getter
- 生命周期 (initialize/shutdown) 有默认空实现
- 执行方法 (execute_step/run_goal) 必须子类实现
- 同步辅助 (get_risk_score/describe_step) 有默认实现
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── 数据类 ──────────────────────────────────────────────


@dataclass
class PluginStep:
    """插件可执行的单个步骤"""
    id: str
    type: str
    payload: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)  # {screenshot, notes}


@dataclass
class PluginStepResult:
    """步骤执行结果"""
    step_id: str
    success: bool
    message: str
    requires_human_review: bool = False
    error: Optional[str] = None


@dataclass
class GoalResult:
    """完整目标执行结果"""
    success: bool
    summary: str
    steps_completed: int = 0
    screenshot_final: str = ""
    error: Optional[str] = None


# ── 抽象基类 ───────────────────────────────────────────


class OpenGuiderPlugin(ABC):
    """插件抽象基类 — 所有插件必须继承并实现全部抽象方法"""

    # ── 身份（子类必须 override）──

    @property
    @abstractmethod
    def id(self) -> str:
        """唯一标识，如 'browser'"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """显示名，如 '浏览器自动化'"""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """语义化版本，如 '1.0.0'"""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> List[str]:
        """此插件可处理的 action type 列表"""
        ...

    # ── 生命周期（有默认实现）──

    async def initialize(self, config: dict) -> None:
        """启动时由 registry 调用一次。默认空实现。"""
        pass

    async def shutdown(self) -> None:
        """退出时由 registry 调用，需在 3 秒内释放资源。默认空实现。"""
        pass

    # ── 执行（子类必须实现）──

    @abstractmethod
    async def execute_step(self, step: PluginStep) -> PluginStepResult:
        """执行单个步骤。由 ExecutionEngine 在审批后调用。"""
        ...

    async def run_goal(self, goal: str, options: dict = None) -> GoalResult:
        """
        自主执行完整目标（插件内部控制）。
        默认抛出 NotImplementedError，子类可选实现。
        """
        raise NotImplementedError(f"{self.id} does not implement run_goal")

    # ── 控制（有默认实现）──

    async def pause(self) -> None:
        """暂停执行。默认空实现。"""
        pass

    async def resume(self) -> None:
        """恢复执行。默认空实现。"""
        pass

    async def abort(self) -> None:
        """立即中止。默认空实现。"""
        pass

    # ── 同步辅助（热路径，必须快）──

    def get_risk_score(self, step: PluginStep) -> int:
        """返回 1-5 风险评分，默认 3（中等）"""
        return 3

    def describe_step(self, step: PluginStep) -> str:
        """一句话描述步骤做什么，默认返回 type"""
        return step.type or "执行操作"


# ── 注册中心（单例）─────────────────────────────────────


class PluginRegistry:
    """插件注册中心，管理所有插件的生命周期"""

    def __init__(self):
        self._plugins: Dict[str, OpenGuiderPlugin] = {}
        self._status: Dict[str, str] = {}  # uninitialized | ok | failed
        self._enabled: Dict[str, bool] = {}

    # ── 注册 ──

    def register(self, plugin: OpenGuiderPlugin) -> None:
        """注册插件，验证必须的 getter 均非空"""
        if not isinstance(plugin, OpenGuiderPlugin):
            raise TypeError("插件必须是 OpenGuiderPlugin 的实例")

        if plugin.id in self._plugins:
            raise ValueError(f"插件 '{plugin.id}' 已注册")

        # 验证必须属性
        for attr in ("id", "name", "version", "capabilities"):
            val = getattr(plugin, attr, None)
            if val is None or (isinstance(val, str) and not val):
                raise ValueError(f"插件 '{plugin.id}' 缺少必须属性: {attr}")
            if attr == "capabilities" and (not isinstance(val, list) or len(val) == 0):
                raise ValueError(f"插件 '{plugin.id}' capabilities 必须是非空列表")

        self._plugins[plugin.id] = plugin
        self._status[plugin.id] = "uninitialized"
        self._enabled[plugin.id] = False

    # ── 查询 ──

    def get(self, plugin_id: str) -> OpenGuiderPlugin:
        """获取指定插件，未注册抛出 KeyError"""
        if plugin_id not in self._plugins:
            raise KeyError(f"插件 '{plugin_id}' 未注册")
        return self._plugins[plugin_id]

    def list_all(self) -> List[OpenGuiderPlugin]:
        """列出全部已注册插件"""
        return list(self._plugins.values())

    def list_status(self) -> List[dict]:
        """列出全部插件及状态（供 API 返回）"""
        return [
            {
                "id": pid,
                "name": plugin.name,
                "version": plugin.version,
                "status": self._status.get(pid, "unknown"),
                "capabilities": plugin.capabilities,
                "enabled": self._enabled.get(pid, False),
            }
            for pid, plugin in self._plugins.items()
        ]

    # ── 生命周期 ──

    async def initialize_all(self, configs: dict = None) -> None:
        """逐个初始化所有已注册插件，单个失败不阻塞其他"""
        configs = configs or {}
        for pid, plugin in self._plugins.items():
            try:
                await plugin.initialize(configs.get(pid, {}))
                self._status[pid] = "ok"
                self._enabled[pid] = True
            except Exception as e:
                self._status[pid] = "failed"

    async def shutdown_all(self) -> None:
        """关闭所有插件，每个最多等待 3 秒"""
        import asyncio
        for pid, plugin in self._plugins.items():
            try:
                await asyncio.wait_for(plugin.shutdown(), timeout=3.0)
                self._status[pid] = "uninitialized"
                self._enabled[pid] = False
            except Exception:
                pass

    async def enable(self, plugin_id: str) -> dict:
        """启用指定插件"""
        plugin = self.get(plugin_id)
        try:
            await plugin.initialize({})
            self._status[plugin_id] = "ok"
            self._enabled[plugin_id] = True
            return {"plugin_id": plugin_id, "status": "ok", "message": "插件已启用"}
        except Exception as e:
            return {"plugin_id": plugin_id, "status": "failed", "message": str(e)}

    async def disable(self, plugin_id: str) -> dict:
        """禁用指定插件"""
        plugin = self.get(plugin_id)
        try:
            import asyncio
            await asyncio.wait_for(plugin.shutdown(), timeout=3.0)
        except Exception:
            pass
        self._status[plugin_id] = "uninitialized"
        self._enabled[plugin_id] = False
        return {"plugin_id": plugin_id, "status": "stopped", "message": "插件已停止"}


# 全局单例
plugin_registry = PluginRegistry()
