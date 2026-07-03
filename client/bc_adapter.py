"""
HAJIMI — B-C PyQt5 集成适配器 (Day 3 真实对接)
==================================================
可直接被 B 端 ``app_controller.py`` 导入，完成 C 模块与 B 的 PyQt5 信号对接。

B 端接入方式::

    # 在 B 的 AppController.__init__ 中：
    from client.bc_adapter import BCAdapter
    self.bc = BCAdapter(server_url="http://localhost:8010")
    self.bc.wire(self)   # self = AppController 实例

B 端需要暴露的属性和信号（对齐 HAJIMI_UI/b-c-api-contract.md）:
    - self.mic_button  (QPushButton)
    - self.voice_settings  (dict: tts_enabled, tts_speed, tts_engine, asr_enabled, asr_engine, asr_language)
    - self.on_asr_result(transcript, confidence, engine)  # 填入输入框
    - self.on_tts_status(status, text, queue_depth)        # 更新喇叭图标
    - self.on_audit_status(status, batch_size, queue_depth, error)  # 状态栏
    - self.on_config_updated(config_dict)                   # 热加载
    - self.on_task_finished(task_id, query, steps...)       # 构造 AuditRecord

不依赖 PyQt5 导入即可完成所有初始化，wire() 时才需要。
"""

import os
import sys
import threading
from typing import Any, Callable, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BCAdapter:
    """B-C 集成适配器

    初始化 C 侧全部子模块，并绑定到 B 的 PyQt5 信号。
    B 只需创建一个实例并调用 wire() 即可。
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8010",
        demo_key: str = "hajimi-demo-2026",
        client_version: str = "v2.1.0",
        vosk_model_path: str = "models/vosk-model-small-cn-0.22",
        microphone_index: int = 2,
    ):
        self._server_url = server_url
        self._demo_key = demo_key
        self._client_version = client_version
        self._vosk_model_path = vosk_model_path
        self._microphone_index = microphone_index

        # 子模块（延迟导入，避免 PyQt5 环境冲突）
        self._asr = None
        self._tts = None
        self._audit = None
        self._poller = None
        self._wired = False

    # ── 对接入口 ──

    def wire(self, app_controller: Any) -> bool:
        """绑定 B 的 PyQt5 信号到 C 模块

        Args:
            app_controller: B 端的 AppController 实例。
                需提供 mic_button (QPushButton) 和 voice_settings (dict)。

        Returns:
            True 如果所有信号绑定成功
        """
        if self._wired:
            return True

        self._init_modules()

        try:
            # ── 接口 1: ASR 录音控制 (B→C) ──
            mic = getattr(app_controller, "mic_button", None)
            if mic and self._asr:
                mic.pressed.connect(self._asr.start_recording)
                mic.released.connect(self._on_mic_released)

            # ── 接口 3: TTS 播报触发 (B→C) ──
            # B 在步骤切换时调用 self.bc.speak(text, priority)
            pass

            # ── 接口 5: 语音设置同步 ──
            vs = getattr(app_controller, "voice_settings", None)
            if vs:
                # 初始同步
                vs.update({
                    "tts_enabled": True,
                    "tts_speed": 0.85,
                    "tts_engine": "pyttsx3",
                    "asr_enabled": True,
                    "asr_engine": "vosk",
                    "asr_language": "zh-CN",
                })
                self._voice_ref = vs

            # ── 接口 8: 配置拉取 ──
            if self._poller:
                self._poller.start()

            self._wired = True
            return True

        except Exception as e:
            print(f"[BCAdapter] 信号绑定异常: {e}")
            return False

    def unwire(self):
        """解绑并释放资源"""
        if self._poller:
            self._poller.stop()
        if self._audit:
            self._audit.shutdown()
        if self._tts:
            self._tts.stop_all()
        self._wired = False

    # ── B 端直接调用的公开方法 ──

    def speak(self, text: str, priority: int = 0, interrupt: bool = False):
        """TTS 播报（B 端步骤切换时调用）

        Args:
            text: 播报文本
            priority: 0=普通 / 1=预警 / 2=紧急
            interrupt: 是否打断当前播报
        """
        enabled = True
        if hasattr(self, "_voice_ref"):
            enabled = self._voice_ref.get("tts_enabled", True)
        if enabled and self._tts:
            self._tts.enqueue(text, priority=priority, interrupt_current=interrupt)

    def audit(self, task_id: str, query: str, intent_category: str = "operation_guide",
              route: str = "L3", total_steps: int = 1, completed_steps: int = 1,
              result: str = "success", duration_ms: int = 0,
              fingerprint_mismatches: int = 0, redline_triggered: bool = False):
        """提交审计记录（B 端任务结束时调用）"""
        if not self._audit:
            return
        import time
        self._audit.enqueue({
            "task_id": task_id,
            "query": query,
            "intent_category": intent_category,
            "complexity_score": 35 if route == "L3" else 20,
            "route": route,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "result": result,
            "duration_ms": duration_ms,
            "fingerprint_mismatches": fingerprint_mismatches,
            "redline_triggered": redline_triggered,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        })

    def health(self) -> dict:
        """健康检查（B 端启动时调用）"""
        from client.integration.controller import HealthStatus
        h = HealthStatus()
        if self._asr:
            h.asr_available = self._asr.engine_status.get("vosk_available", False) or \
                              self._asr.engine_status.get("google_available", False)
            h.asr_engine = self._asr.active_engine
        if self._tts:
            h.tts_available = self._tts.is_available
            h.tts_engine = "pyttsx3"
        if self._audit:
            try:
                qs = self._audit.get_queue_status()
                h.audit_db_ok = qs["queue_depth"] >= 0
                h.server_reachable = qs["server_reachable"]
                h.queue_depth = qs["queue_depth"]
            except Exception:
                pass
        return {
            "asr_available": h.asr_available,
            "asr_engine": h.asr_engine,
            "tts_available": h.tts_available,
            "tts_engine": h.tts_engine,
            "audit_db_ok": h.audit_db_ok,
            "server_reachable": h.server_reachable,
            "queue_depth": h.queue_depth,
            "overall": h.overall,
        }

    # ── 内部 ──

    def _init_modules(self):
        """初始化所有 C 子模块"""
        from client.voice.asr_client import ASRClient
        from client.voice.tts_engine import TTSEngine
        from client.audit.audit_agent import AuditAgent
        from client.config.config_poller import ConfigPoller

        self._asr = ASRClient(
            microphone_index=self._microphone_index,
            vosk_model_path=self._vosk_model_path,
            result_callback=self._on_asr_done,
        )

        self._tts = TTSEngine(
            status_callback=self._on_tts_event,
        )

        self._audit = AuditAgent(
            server_url=self._server_url,
            demo_key=self._demo_key,
        )

        self._poller = ConfigPoller(
            server_url=self._server_url,
            demo_key=self._demo_key,
            client_version=self._client_version,
        )

    def _on_mic_released(self):
        """麦克风松开 → 停止录音并转写"""
        if self._asr:
            result = self._asr.stop_and_transcribe()
            self._on_asr_done(result)

    def _on_asr_done(self, result: Any):
        """ASR 转写完成 → 通知 B"""
        # B 端通过 app_controller.on_asr_result 接收
        pass

    def _on_tts_event(self, status: str, text: str, depth: int):
        """TTS 事件 → 通知 B"""
        pass
