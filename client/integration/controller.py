"""
HAJIMI Client — B-C 集成控制器 (VoiceIntegrationController)
==============================================================
按照 B-C 接口契约 §四 定义，将 B 的信号与 C 的槽函数绑定。

在 PyQt5 桌面进程中初始化时调用一次:

    from client.integration.controller import VoiceIntegrationController

    controller = VoiceIntegrationController(
        server_url="http://localhost:8000",
        demo_key="hajimi-demo-2026",
    )
    # 连接到 B 的信号
    controller.bind_to(b_signals, shared_state)
    # 启动后台服务
    controller.start()

    # 健康检查
    health = controller.health_check()

非 PyQt5 环境下可独立使用（信号连接为 no-op），方便独立测试各子模块。
"""

import threading
from dataclasses import dataclass
from typing import Optional, Dict, Any


# ────────────────────────── 健康状态模型 ──────────────────────────


@dataclass
class HealthStatus:
    """C 各子模块健康状态（对应 B-C 接口契约 §接口9）"""
    asr_available: bool = False
    asr_engine: str = "mock"
    tts_available: bool = False
    tts_engine: str = "pyttsx3"
    audit_db_ok: bool = False
    server_reachable: bool = False
    queue_depth: int = 0

    @property
    def overall(self) -> str:
        """综合健康评级"""
        criticals = [self.asr_available, self.tts_available]
        if not any(criticals):
            return "unhealthy"
        if not self.server_reachable or not self.audit_db_ok:
            return "degraded"
        if not all(criticals):
            return "degraded"
        return "healthy"


# ────────────────────────── 集成控制器 ──────────────────────────


class VoiceIntegrationController:
    """B-C 集成控制器

    初始化 C 侧全部子模块（ASR、TTS、审计代理、配置轮询），
    并将 B 的 Qt 信号绑定到对应的处理函数。

    严格按照 B-C 接口契约 §四 "信号注册总表" 实现。
    """

    # 默认语音设置（B-C 接口契约 §接口5）
    DEFAULT_VOICE_SETTINGS: Dict[str, Any] = {
        "tts_enabled": True,
        "tts_speed": 0.85,
        "tts_engine": "pyttsx3",
        "asr_enabled": True,
        "asr_engine": "vosk",
        "asr_language": "zh-CN",
    }

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        demo_key: str = "hajimi-demo-2026",
        client_version: str = "v2.1.0",
    ):
        self._server_url = server_url
        self._demo_key = demo_key
        self._client_version = client_version

        # 子模块（延迟初始化）
        self._asr_client = None
        self._tts_engine = None
        self._audit_agent = None
        self._config_poller = None

        # B 的信号引用（PyQt5 绑定后设置）
        self._b_signals = None
        self._voice_settings = dict(self.DEFAULT_VOICE_SETTINGS)
        self._settings_lock = threading.Lock()

        # 运行状态
        self._started = False

    # ────────────────────────── 生命周期 ──────────────────────────

    def start(self) -> None:
        """启动所有 C 子模块的后台服务"""
        if self._started:
            return
        self._started = True

        # 延迟导入以确保所有依赖就绪
        from client.voice.asr_client import ASRClient, ASREngine
        from client.voice.tts_engine import TTSEngine
        from client.audit.audit_agent import AuditAgent
        from client.config.config_poller import ConfigPoller

        # ASR
        asr_engine = self._voice_settings.get("asr_engine", "vosk")
        self._asr_client = ASRClient(
            result_callback=self._on_asr_result,
            engine=asr_engine,
            language=self._voice_settings.get("asr_language", "zh-CN"),
        )

        # TTS
        self._tts_engine = TTSEngine(
            status_callback=self._on_tts_status,
            engine=self._voice_settings.get("tts_engine", "pyttsx3"),
            rate=int(self._voice_settings.get("tts_speed", 0.85) * 200),
        )

        # 审计代理
        self._audit_agent = AuditAgent(
            db_path="client/audit/audit_queue.db",
            server_url=self._server_url,
            demo_key=self._demo_key,
            status_callback=self._on_audit_status,
        )

        # 配置轮询
        poll_interval = self._voice_settings.get("config_pull_interval_min", 30)
        self._config_poller = ConfigPoller(
            server_url=self._server_url,
            demo_key=self._demo_key,
            client_version=self._client_version,
            interval_min=poll_interval,
            on_config_changed=self._on_config_changed,
        )
        self._config_poller.start()

    def shutdown(self) -> None:
        """关闭所有 C 子模块"""
        self._started = False
        if self._asr_client:
            self._asr_client.cancel()
        if self._tts_engine:
            self._tts_engine.shutdown()
        if self._audit_agent:
            self._audit_agent.shutdown()
        if self._config_poller:
            self._config_poller.shutdown()

    # ────────────────────────── 信号绑定 ──────────────────────────

    def bind_to(self, b_signals: Any, shared_state: Optional[Dict] = None) -> None:
        """将 B 的信号连接到 C 的处理函数

        Args:
            b_signals: B 侧信号集合对象，需包含以下信号属性：
                - asr_start / asr_stop (pyqtSignal)
                - tts_enqueue (pyqtSignal)
                - audit_submit (pyqtSignal)
                - health_check_request (pyqtSignal, optional)
            shared_state: 共享状态 dict，需包含 'voice_settings' key
        """
        self._b_signals = b_signals

        # 更新共享状态
        if shared_state:
            if "voice_settings" in shared_state:
                with self._settings_lock:
                    self._voice_settings.update(shared_state["voice_settings"])

        # 尝试绑定 PyQt5 信号（如果可用）
        if self._has_pyqt_signals(b_signals):
            self._bind_qt_signals(b_signals)
        else:
            # 非 PyQt5 环境：跳过信号绑定，模块仍可通过方法调用使用
            pass

    @staticmethod
    def _has_pyqt_signals(b_signals: Any) -> bool:
        """检查是否存在 PyQt5 信号"""
        try:
            return hasattr(b_signals, "asr_start") and hasattr(b_signals, "connect")
        except Exception:
            return False

    def _bind_qt_signals(self, b_signals: Any) -> None:
        """执行 Qt 信号绑定"""
        try:
            # 需要子模块已初始化
            if not self._started:
                return

            # ASR（B-C 接口 §接口1-2）
            if self._asr_client and hasattr(b_signals, "asr_start"):
                b_signals.asr_start.connect(self._asr_client.start_recording)
            if self._asr_client and hasattr(b_signals, "asr_stop"):
                b_signals.asr_stop.connect(self._on_asr_stop)

            # TTS（B-C 接口 §接口3）
            if self._tts_engine and hasattr(b_signals, "tts_enqueue"):
                b_signals.tts_enqueue.connect(self._on_tts_enqueue)

            # 审计（B-C 接口 §接口6）
            if self._audit_agent and hasattr(b_signals, "audit_submit"):
                b_signals.audit_submit.connect(self._audit_agent.enqueue)

            # 健康检查（B-C 接口 §接口9）
            if hasattr(b_signals, "health_check_request"):
                b_signals.health_check_request.connect(self._handle_health_request)

        except Exception:
            # 信号绑定失败不阻塞启动
            pass

    # ────────────────────────── 回调处理 ──────────────────────────

    def _on_asr_result(self, result: Any) -> None:
        """ASR 转写结果 → 回传给 B（B-C 接口 §接口2）"""
        if self._b_signals and hasattr(self._b_signals, "asr_result"):
            try:
                # 构造回调数据
                data = {
                    "transcript": getattr(result, "transcript", ""),
                    "confidence": getattr(result, "confidence", 0.0),
                    "engine": getattr(result, "engine", "mock"),
                    "error": getattr(result, "error", None),
                }
                self._b_signals.asr_result.emit(data)
            except Exception:
                pass

    def _on_asr_stop(self) -> None:
        """B 松开麦克风按钮 → 停止录音并转写"""
        if self._asr_client:
            result = self._asr_client.stop_and_transcribe()
            self._on_asr_result(result)

    def _on_tts_enqueue(
        self,
        text: str,
        priority: int = 0,
        interrupt_current: bool = False,
    ) -> None:
        """B 触发 TTS 播报 → 入队"""
        if not self._voice_settings.get("tts_enabled", True):
            return
        if self._tts_engine:
            self._tts_engine.enqueue(
                text,
                priority=priority,
                interrupt_current=interrupt_current,
            )

    def _on_tts_status(self, status: str, text: str, queue_depth: int) -> None:
        """TTS 状态变更 → 回传给 B（B-C 接口 §接口4）"""
        if self._b_signals and hasattr(self._b_signals, "tts_status"):
            try:
                self._b_signals.tts_status.emit(status, text, queue_depth)
            except Exception:
                pass

    def _on_audit_status(
        self,
        status: str,
        batch_size: int,
        queue_depth: int,
        error: Optional[str],
    ) -> None:
        """审计上报状态 → 回传给 B（B-C 接口 §接口7）"""
        if self._b_signals and hasattr(self._b_signals, "audit_status"):
            try:
                self._b_signals.audit_status.emit(
                    status, batch_size, queue_depth, error
                )
            except Exception:
                pass

    def _on_config_changed(self, config: Dict[str, Any]) -> None:
        """配置变更 → 回传给 B（B-C 接口 §接口8）"""
        # 1. 更新本地语音设置
        new_interval = config.get("config_pull_interval_min")
        if new_interval and self._config_poller:
            self._config_poller.set_interval(new_interval)

        # 2. 通知 B
        if self._b_signals and hasattr(self._b_signals, "config_updated"):
            try:
                self._b_signals.config_updated.emit(config)
            except Exception:
                pass

    def _handle_health_request(self) -> None:
        """B 请求健康检查 → 返回 HealthStatus"""
        if self._b_signals and hasattr(self._b_signals, "health_result"):
            try:
                health = self.health_check()
                self._b_signals.health_result.emit(health)
            except Exception:
                pass

    # ────────────────────────── 健康检查 ──────────────────────────

    def health_check(self) -> HealthStatus:
        """返回 C 各子模块健康状态（B-C 接口 §接口9）"""
        status = HealthStatus()

        # ASR
        if self._asr_client:
            engine_info = getattr(self._asr_client, "engine_status", {})
            status.asr_available = engine_info.get("vosk_available", False) or engine_info.get("google_available", False)
            status.asr_engine = engine_info.get("active_engine", "mock")

        # TTS
        if self._tts_engine:
            status.tts_available = getattr(self._tts_engine, "is_available", False)
            status.tts_engine = self._voice_settings.get("tts_engine", "pyttsx3")

        # 审计
        if self._audit_agent:
            try:
                queue_status = self._audit_agent.get_queue_status()
                status.audit_db_ok = queue_status.get("queue_depth", -1) >= 0
                status.server_reachable = queue_status.get("server_reachable", False)
                status.queue_depth = queue_status.get("queue_depth", 0)
            except Exception:
                pass

        return status

    # ────────────────────────── 语音设置 ──────────────────────────

    def get_voice_settings(self) -> Dict[str, Any]:
        """获取当前语音设置"""
        with self._settings_lock:
            return dict(self._voice_settings)

    def update_voice_setting(self, key: str, value: Any) -> None:
        """更新单项语音设置并立即生效"""
        with self._settings_lock:
            if key in self._voice_settings:
                self._voice_settings[key] = value

        # 即时生效
        if key == "tts_speed" and self._tts_engine:
            self._tts_engine.set_rate(int(value * 200))
        elif key == "tts_engine" and self._tts_engine:
            pass  # 引擎切换需要重启 TTS，暂不支持热切换
        elif key == "config_pull_interval_min" and self._config_poller:
            self._config_poller.set_interval(value)
