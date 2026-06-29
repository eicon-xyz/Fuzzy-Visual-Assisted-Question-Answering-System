"""
HAJIMI Client — 配置轮询 (ConfigPoller) 模块
===============================================
定时轮询 ``GET /api/config/pull``，支持 ETag 条件请求，检测变更后通知

严格按照 A-C 接口契约 §3.2 + B-C 接口契约 §接口8 定义实现。

用法::

    from client.config.config_poller import ConfigPoller

    poller = ConfigPoller(
        server_url="http://localhost:8000",
        demo_key="hajimi-demo-2026",
        client_version="v2.1.0",
        interval_min=30,
        on_config_changed=lambda config: print(f"新配置: {config['version']}"),
    )
    poller.start()
    # ... 运行中 ...
    poller.stop()
"""

import json
import threading
import time
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field


# ────────────────────────── 类型 ──────────────────────────

# on_config_changed(config: dict) — 服务端有新配置时回调
ConfigChangedCallback = Callable[[Dict[str, Any]], None]

# on_error(error: str) — 轮询出错时回调
ConfigErrorCallback = Callable[[str], None]


@dataclass
class PollerState:
    """轮询器运行时状态"""
    running: bool = False
    last_etag: str = ""
    last_version: str = ""
    last_poll_at: float = 0.0
    consecutive_errors: int = 0
    current_config: Dict[str, Any] = field(default_factory=dict)


class ConfigPoller:
    """配置轮询器

    定时（默认 30 分钟）向服务端拉取最新配置。支持：
    - ETag/If-None-Match 条件请求（304 节省带宽）
    - 版本号比对，变更时回调通知
    - 连续失败降级（使用本地缓存继续工作）
    """

    DEFAULT_INTERVAL_MIN = 30
    MIN_INTERVAL_MIN = 5
    MAX_INTERVAL_MIN = 1440  # 最长 24 小时

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        demo_key: str = "hajimi-demo-2026",
        client_version: str = "v2.1.0",
        interval_min: int = DEFAULT_INTERVAL_MIN,
        on_config_changed: Optional[ConfigChangedCallback] = None,
        on_error: Optional[ConfigErrorCallback] = None,
    ):
        self._server_url = server_url.rstrip("/")
        self._demo_key = demo_key
        self._client_version = client_version
        self._interval = max(self.MIN_INTERVAL_MIN, min(self.MAX_INTERVAL_MIN, interval_min))
        self._on_changed = on_config_changed
        self._on_error = on_error

        self._state = PollerState()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        # HTTP 客户端
        self._httpx_available = False
        try:
            import httpx
            self._http = httpx.Client(timeout=15.0)
            self._httpx_available = True
        except ImportError:
            self._http = None

    # ────────────────────────── 公开 API ──────────────────────────

    @property
    def running(self) -> bool:
        return self._state.running

    @property
    def current_config(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state.current_config)

    @property
    def last_version(self) -> str:
        return self._state.last_version

    @property
    def interval_min(self) -> int:
        return self._interval

    def start(self) -> None:
        """启动定时轮询（后台线程）"""
        if self._state.running:
            return
        self._state.running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="config-poller"
        )
        self._thread.start()

    def stop(self) -> None:
        """停止轮询"""
        self._state.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def poll_now(self) -> Optional[Dict[str, Any]]:
        """手动立即拉取配置（同步阻塞）

        Returns:
            最新配置 dict，无更新返回 None，失败返回 None
        """
        return self._do_poll()

    def set_interval(self, minutes: int) -> None:
        """动态调整轮询间隔（由服务端配置下发触发）"""
        self._interval = max(
            self.MIN_INTERVAL_MIN,
            min(self.MAX_INTERVAL_MIN, minutes),
        )

    def get_state(self) -> Dict[str, Any]:
        """获取轮询器运行状态"""
        return {
            "running": self._state.running,
            "interval_min": self._interval,
            "last_etag": self._state.last_etag,
            "last_version": self._state.last_version,
            "last_poll_at": self._state.last_poll_at,
            "consecutive_errors": self._state.consecutive_errors,
        }

    def shutdown(self) -> None:
        """关闭轮询器，释放资源"""
        self.stop()
        if self._http:
            self._http.close()

    # ────────────────────────── 内部实现 ──────────────────────────

    def _poll_loop(self) -> None:
        """后台轮询循环"""
        while self._state.running:
            self._do_poll()
            # 分片睡眠以响应 stop 信号
            deadline = time.monotonic() + (self._interval * 60)
            while self._state.running and time.monotonic() < deadline:
                time.sleep(min(1.0, deadline - time.monotonic()))

    def _do_poll(self) -> Optional[Dict[str, Any]]:
        """执行一次配置拉取"""
        if not self._httpx_available:
            self._emit_error("httpx 不可用，跳过配置拉取")
            return None

        self._state.last_poll_at = time.time()

        headers = {
            "X-Demo-Key": self._demo_key,
            "X-Client-Version": self._client_version,
        }
        if self._state.last_etag:
            headers["If-None-Match"] = self._state.last_etag

        try:
            r = self._http.get(
                f"{self._server_url}/api/config/pull",
                headers=headers,
            )

            # 304 Not Modified
            if r.status_code == 304:
                self._state.consecutive_errors = 0
                return None

            r.raise_for_status()
            data = r.json()

            # 检查 ETag
            new_etag = r.headers.get("ETag", "")
            if new_etag:
                self._state.last_etag = new_etag

            self._state.consecutive_errors = 0

            # 判断是否有更新
            if data.get("has_update") and data.get("config"):
                new_config = data["config"]
                new_version = new_config.get("version", "")

                if new_version and new_version != self._state.last_version:
                    self._state.last_version = new_version
                    with self._lock:
                        self._state.current_config = new_config

                    # 如果配置中指定了新轮询间隔，应用之
                    new_interval = new_config.get("config_pull_interval_min")
                    if new_interval is not None:
                        self.set_interval(new_interval)

                    self._notify_changed(new_config)
                    return new_config

                # 即使版本号相同也更新缓存
                with self._lock:
                    self._state.current_config = new_config
                return new_config

            return None

        except Exception as e:
            self._state.consecutive_errors += 1
            self._emit_error(f"配置拉取失败 (连续 {self._state.consecutive_errors} 次): {e}")
            return None

    def _notify_changed(self, config: Dict[str, Any]) -> None:
        """通知配置变更"""
        if self._on_changed:
            try:
                self._on_changed(config)
            except Exception:
                pass

    def _emit_error(self, error: str) -> None:
        """通知错误"""
        if self._on_error:
            try:
                self._on_error(error)
            except Exception:
                pass
