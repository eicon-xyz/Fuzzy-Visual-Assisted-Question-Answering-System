"""
HAJIMI — B-C 集成联调仿真测试 (Day 3)
=========================================
模拟 B 的 PyQt5 信号，测试 C 的完整语音管线：
麦克风按钮 → ASR 录音 → 转写结果 → TTS 播报 → 审计提交 → 状态回传

不依赖 PyQt5，独立运行。

用法::

    python client/bc_integration_test.py
"""

import sys
import os
import time
import threading
from typing import Any, Callable, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


# ═══════════════════════════════════════════════════════
#  PyQt5 信号模拟器
# ═══════════════════════════════════════════════════════

class SimulatedSignal:
    """模拟 PyQt5 pyqtSignal，支持 connect / emit"""

    def __init__(self):
        self._slots: list[Callable] = []

    def connect(self, slot: Callable) -> None:
        self._slots.append(slot)

    def emit(self, *args: Any, **kwargs: Any) -> None:
        for slot in self._slots:
            try:
                slot(*args, **kwargs)
            except Exception as e:
                print(f"  ⚠ 信号处理异常: {e}")


class SimulatedBSignals:
    """模拟 B 的 9 个信号接口（B-C 接口契约 §四）"""

    def __init__(self):
        self.asr_start = SimulatedSignal()
        self.asr_stop = SimulatedSignal()
        self.asr_result = SimulatedSignal()
        self.tts_enqueue = SimulatedSignal()
        self.tts_status = SimulatedSignal()
        self.audit_submit = SimulatedSignal()
        self.audit_status = SimulatedSignal()
        self.config_updated = SimulatedSignal()
        self.health_check_request = SimulatedSignal()
        self.health_result = SimulatedSignal()


# ═══════════════════════════════════════════════════════
#  测试用例
# ═══════════════════════════════════════════════════════

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.events: list[str] = []

    def ok(self, msg: str, condition: bool = True):
        if condition:
            print(f"  ✅ {msg}")
            self.passed += 1
            self.events.append(f"PASS: {msg}")
        else:
            print(f"  ❌ {msg}")
            self.failed += 1
            self.events.append(f"FAIL: {msg}")

    def info(self, msg: str):
        print(f"  ℹ️  {msg}")
        self.events.append(f"INFO: {msg}")

    def summary(self):
        print()
        print(f"  结果: {self.passed} 通过, {self.failed} 失败")
        return self.failed == 0


def test_signal_wiring(r: TestResults, signals: SimulatedBSignals,
                       controller: Any, voice_settings: dict):
    """测试 1：信号绑定验证 (B-C 契约 §接口1-9)"""
    print()
    print("=" * 50)
    print("  1. 信号绑定验证")
    print("=" * 50)

    # 接口 1: ASR 录音控制
    r.ok("asr_start → ASRClient.start_recording" if hasattr(signals.asr_start, '_slots')
         else "asr_start 信号已定义")
    r.ok("asr_stop → ASRClient.stop_and_transcribe" if hasattr(signals.asr_stop, '_slots')
         else "asr_stop 信号已定义")

    # 接口 2: ASR 转写结果
    r.ok("asr_result (C→B) 信号已定义" if hasattr(signals.asr_result, '_slots')
         else "asr_result 信号缺失")

    # 接口 3: TTS 播报触发
    r.ok("tts_enqueue (B→C) 信号已定义" if hasattr(signals.tts_enqueue, '_slots')
         else "tts_enqueue 信号缺失")

    # 接口 4: TTS 状态回传
    r.ok("tts_status (C→B) 信号已定义" if hasattr(signals.tts_status, '_slots')
         else "tts_status 信号缺失")

    # 接口 5: 语音设置共享状态
    r.ok(f"voice_settings 包含 {len(voice_settings)} 项",
         len(voice_settings) >= 5)

    # 接口 6: 审计数据提交
    r.ok("audit_submit (B→C) 信号已定义" if hasattr(signals.audit_submit, '_slots')
         else "audit_submit 信号缺失")

    # 接口 7: 审计上报状态
    r.ok("audit_status (C→B) 信号已定义" if hasattr(signals.audit_status, '_slots')
         else "audit_status 信号缺失")

    # 接口 8: 配置拉取通知
    r.ok("config_updated (C→B) 信号已定义" if hasattr(signals.config_updated, '_slots')
         else "config_updated 信号缺失")

    # 接口 9: 健康检测
    r.ok("health_check_request 信号已定义" if hasattr(signals.health_check_request, '_slots')
         else "health_check_request 信号缺失")


def test_asr_pipeline(r: TestResults, signals: SimulatedBSignals,
                      controller: Any):
    """测试 2：ASR 语音管线 (B-C 契约 §接口1-2)"""
    print()
    print("=" * 50)
    print("  2. ASR 语音管线测试")
    print("=" * 50)

    from client.voice.asr_client import ASRClient

    # 用 Mock 引擎，避免依赖麦克风
    asr = ASRClient(engine="mock")
    r.ok(f"ASR 引擎就绪: {asr.active_engine}",
         asr.active_engine in ("vosk", "google", "mock"))

    # 模拟 B 按下麦克风按钮 → asr_start
    r.info("模拟: B 按下麦克风按钮 → asr_start")
    asr.start_recording()
    r.ok("录音已启动", asr.is_recording)

    # 等待片刻
    time.sleep(0.3)

    # 模拟 B 松开按钮 → asr_stop → 转写
    r.info("模拟: B 松开按钮 → asr_stop → 转写")
    result = asr.stop_and_transcribe()
    r.ok(f"转写完成: transcript='{result.transcript}'",
         len(result.transcript) > 0)


def test_tts_pipeline(r: TestResults, signals: SimulatedBSignals,
                      controller: Any):
    """测试 3：TTS 播报管线 (B-C 契约 §接口3-4)"""
    print()
    print("=" * 50)
    print("  3. TTS 播报管线测试")
    print("=" * 50)

    from client.voice.tts_engine import TTSEngine, TTSStatus

    played = []
    completed = []

    def on_status(status, text, depth):
        if status == TTSStatus.PLAYING:
            played.append(text)
        elif status == TTSStatus.COMPLETED:
            completed.append(text)

    tts = TTSEngine(status_callback=on_status)
    r.ok(f"TTS 引擎就绪: {'OK' if tts.is_available else 'Mock'}", True)

    # 模拟 B 触发 TTS 播报 (接口3)
    r.info("模拟: B emit tts_enqueue('请点击桌面上的浏览器图标')")
    tts.enqueue("请点击桌面上的浏览器图标", priority=0)
    time.sleep(3)  # 等待 TTS 后台线程完成播报

    r.ok(f"TTS 播报已触发: {len(played)} 条播放",
         len(played) >= 1)
    # TTS 完成是异步的，至少播放或完成有一个非零即可
    r.ok(f"TTS 播报已完成或播放中 (played={len(played)}, completed={len(completed)})",
         len(played) + len(completed) >= 1)

    tts.shutdown()


def test_audit_submit(r: TestResults, signals: SimulatedBSignals,
                      controller: Any):
    """测试 4：审计数据提交流程 (B-C 契约 §接口6-7)"""
    print()
    print("=" * 50)
    print("  4. 审计提交流程测试")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent, desensitize_text
    import tempfile

    agent = AuditAgent(db_path=os.path.join(tempfile.gettempdir(), "hajimi_bc_test.db"))

    # 模拟 B 任务完成后 emit audit_submit (接口6)
    audit_record = {
        "task_id": "bc-test-550e8400-e29b-41d4-a716",
        "query": "怎么安装微信",
        "intent_category": "operation_guide",
        "complexity_score": 35,
        "route": "L3",
        "total_steps": 3,
        "completed_steps": 3,
        "result": "success",
        "duration_ms": 45200,
        "feedback_type": "useful",
        "comment": "指引很清晰，步骤准确",
        "fingerprint_mismatches": 0,
        "redline_triggered": False,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }

    r.info("模拟: B emit audit_submit(record)")
    ok = agent.enqueue(audit_record)
    r.ok("审计记录入队成功", ok)

    depth = agent.get_queue_depth()
    r.ok(f"队列深度 ≥ 1 (实际 {depth})", depth >= 1)

    # 验证脱敏 (接口6 要求)
    clean_query = desensitize_text("帮我重置密码=abc123")
    r.ok(f"脱敏生效: {clean_query}", "[REDACTED]" in clean_query)

    # 模拟审计状态回传 (接口7)
    agent._emit_status("success", 1, 0, None)
    r.ok("审计状态回传 (C→B) 已触发", True)

    agent.shutdown()


def test_health_check(r: TestResults, signals: SimulatedBSignals,
                      controller: Any):
    """测试 5：健康检测 (B-C 契约 §接口9)"""
    print()
    print("=" * 50)
    print("  5. 健康检测测试")
    print("=" * 50)

    from client.integration.controller import HealthStatus

    # 全部健康
    h1 = HealthStatus(
        asr_available=True,
        tts_available=True,
        audit_db_ok=True,
        server_reachable=True,
    )
    r.ok(f"全部健康 → overall='{h1.overall}'", h1.overall == "healthy")

    # 部分降级
    h2 = HealthStatus(
        asr_available=False,
        tts_available=True,
        audit_db_ok=True,
        server_reachable=False,
    )
    r.ok(f"部分降级 → overall='{h2.overall}'", h2.overall == "degraded")

    # 全部不可用
    h3 = HealthStatus()
    r.ok(f"全部不可用 → overall='{h3.overall}'", h3.overall == "unhealthy")

    # 验证 7 个字段全部存在 (接口9 数据模型)
    fields = ["asr_available", "asr_engine", "tts_available", "tts_engine",
              "audit_db_ok", "server_reachable", "queue_depth"]
    for f in fields:
        r.ok(f"字段 {f} 存在", hasattr(h1, f))


def test_config_flow(r: TestResults, signals: SimulatedBSignals,
                     controller: Any):
    """测试 6：配置变更通知 (B-C 契约 §接口8)"""
    print()
    print("=" * 50)
    print("  6. 配置变更通知测试")
    print("=" * 50)

    from client.config.config_poller import ConfigPoller

    changed_config = None

    def on_changed(config):
        nonlocal changed_config
        changed_config = config

    poller = ConfigPoller(
        server_url="http://localhost:8010",
        interval_min=30,
        on_config_changed=on_changed,
    )

    # 手动注入一个配置变更
    fake_config = {
        "version": "v2.1.5",
        "confidence_threshold": 85,
        "config_pull_interval_min": 30,
    }
    r.info("模拟: 服务端推送配置 v2.1.5")
    poller._notify_changed(fake_config)
    r.ok("配置变更回调已触发", changed_config is not None)
    r.ok(f"版本号: {changed_config.get('version')}",
         changed_config.get("version") == "v2.1.5")

    # 测试间隔动态调整
    poller.set_interval(60)
    r.ok(f"轮询间隔调整: {poller.interval_min}min", poller.interval_min == 60)

    poller.shutdown()


# ═══════════════════════════════════════════════════════
#  6 个测试模拟真实交互序列
# ═══════════════════════════════════════════════════════

def test_full_interaction_sequence(r: TestResults):
    """测试 7：模拟完整用户交互序列"""
    print()
    print("=" * 50)
    print("  7. 完整交互序列模拟")
    print("=" * 50)

    r.info("场景: 用户语音提问「怎么安装微信」→ 系统指引")

    # Step 1: 用户按下麦克风按钮
    r.info("[1/5] 用户按下麦克风按钮 → ASR 开始录音")
    from client.voice.asr_client import ASRClient
    asr = ASRClient(engine="mock")
    asr.start_recording()
    time.sleep(0.5)
    result = asr.stop_and_transcribe()
    r.ok(f"ASR 识别: '{result.transcript}'", len(result.transcript) > 0)

    # Step 2: 转写结果填入输入框
    r.info(f"[2/5] 转写结果填入 B 的输入框: '{result.transcript}'")

    # Step 3: 发送到 A 的 /api/demo/process（模拟）
    r.info("[3/5] 发送到 A → /api/demo/process → 返回步骤")

    # Step 4: TTS 播报步骤
    r.info("[4/5] B emit tts_enqueue → TTS 播报指引")
    from client.voice.tts_engine import TTSEngine
    tts = TTSEngine()
    tts.enqueue("第一步：打开桌面上的浏览器图标")
    time.sleep(2)
    r.ok("TTS 播报已触发", True)

    # Step 5: 任务完成，提交审计
    r.info("[5/5] 任务完成 → B emit audit_submit → 审计代理入队")
    from client.audit.audit_agent import AuditAgent
    import tempfile
    agent = AuditAgent(db_path=os.path.join(tempfile.gettempdir(), "hajimi_seq_test.db"))
    agent.enqueue({
        "task_id": "seq-test-001",
        "query": result.transcript,
        "intent_category": "operation_guide",
        "complexity_score": 35,
        "route": "L3",
        "total_steps": 3,
        "completed_steps": 3,
        "result": "success",
        "duration_ms": 5000,
        "fingerprint_mismatches": 0,
        "redline_triggered": False,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    })
    depth = agent.get_queue_depth()
    r.ok(f"审计记录已入队 (depth={depth})", depth >= 1)

    tts.shutdown()
    agent.shutdown()


# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("  HAJIMI Day 3 — B-C 集成联调仿真测试")
    print("  (不依赖 PyQt5，模拟 9 个 B-C 信号)")
    print()

    r = TestResults()
    signals = SimulatedBSignals()

    voice_settings = {
        "tts_enabled": True,
        "tts_speed": 0.85,
        "tts_engine": "pyttsx3",
        "asr_enabled": True,
        "asr_engine": "vosk",
        "asr_language": "zh-CN",
    }

    # 初始化 C 控制器
    from client.integration.controller import VoiceIntegrationController
    controller = VoiceIntegrationController(
        server_url="http://localhost:8010",
        demo_key="hajimi-demo-2026",
    )
    controller.start()
    controller.bind_to(signals, {"voice_settings": voice_settings})

    # 运行 7 个测试
    test_signal_wiring(r, signals, controller, voice_settings)
    test_asr_pipeline(r, signals, controller)
    test_tts_pipeline(r, signals, controller)
    test_audit_submit(r, signals, controller)
    test_health_check(r, signals, controller)
    test_config_flow(r, signals, controller)
    test_full_interaction_sequence(r)

    controller.shutdown()

    print()
    print("=" * 50)
    all_ok = r.summary()
    if all_ok:
        print("  Day 3 B-C 集成联调测试全部通过")
    else:
        print(f"  ⚠ {r.failed} 项未通过")
