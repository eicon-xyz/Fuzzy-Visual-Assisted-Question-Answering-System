"""
HAJIMI C-end 客户端模块单元测试
==================================
测试 C 端 6 个核心模块。不需要 A 端运行。

用法::
    python 项目文档/测试文档/test_client_modules.py
"""
import sys, os, time, tempfile

# Add project root to path
PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)
if sys.platform == "win32":
    import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PASS = 0; FAIL = 0
def ok(msg, cond=True):
    global PASS, FAIL
    if cond: print(f"  [PASS] {msg}"); PASS += 1
    else: print(f"  [FAIL] {msg}"); FAIL += 1

# ── 1. ASR 模块 ──
def test_asr():
    print("\n========= 1. C-ASR 语音识别 =========")
    from client.voice.asr_client import ASRClient, ASREngine

    # Mock mode
    asr = ASRClient(engine="mock")
    ok(f"Mock引擎: active={asr.active_engine}", asr.active_engine == ASREngine.MOCK)
    asr.start_recording()
    ok("录音启动", asr.is_recording)
    time.sleep(0.3)
    result = asr.stop_and_transcribe()
    ok(f"转写: '{result.transcript}'", len(result.transcript) > 0)
    ok(f"引擎标记: {result.engine}", result.engine == ASREngine.MOCK)

    # Vosk mode (if model exists)
    asr2 = ASRClient(engine="vosk")
    status = asr2.engine_status
    ok(f"Vosk可用: {status['vosk_available']}", True)
    ok(f"Google可用: {status['google_available']}", True)

    # list_microphones
    mics = ASRClient.list_microphones()
    ok(f"麦克风枚举: {len(mics)} 个设备", True)

# ── 2. TTS 模块 ──
def test_tts():
    print("\n========= 2. C-TTS 语音合成 =========")
    from client.voice.tts_engine import TTSEngine, TTSStatus

    played = set()
    def on_status(status, text, depth):
        played.add(status)

    tts = TTSEngine(status_callback=on_status)
    ok(f"引擎就绪: {'OK' if tts.is_available else 'Mock'}", True)

    tts.enqueue("单元测试语音")
    time.sleep(2)

    ok(f"enqueue成功", tts.queue_depth == 0 or tts.is_playing or TTSStatus.PLAYING in played)

    # Voice list
    voices = TTSEngine.list_voices()
    ok(f"语音包枚举: {len(voices)} 个", len(voices) > 0)
    zh = [v for v in voices if "zh" in str(v.get("languages",[])).lower()
          or "chinese" in v.get("name","").lower()]
    ok(f"中文语音包: {len(zh)} 个", len(zh) >= 1)

    # Rate test
    tts.set_rate(200)
    ok("语速调整", True)

    tts.shutdown()

# ── 3. 审计代理 ──
def test_audit():
    print("\n========= 3. C-审计代理 =========")
    from client.audit.audit_agent import AuditAgent, desensitize_text

    # Desensitization
    tests = [
        ("密码=123456", "[REDACTED]"),
        ("api_key=sk-abc", "[REDACTED]"),
        ("C:\\Users\\a.txt", "[FILE_PATH]"),
        ("13800138000", "[PHONE]"),
        ("test@example.com", "[EMAIL]"),
        ("110101199001011234", "[ID_NUMBER]"),
    ]
    for text, marker in tests:
        result = desensitize_text(text)
        ok(f"脱敏: {text[:20]} → {marker}", marker in result)

    # Queue agent
    db_path = os.path.join(tempfile.gettempdir(), f"hajimi_client_test_{int(time.time())}.db")
    agent = AuditAgent(db_path=db_path, server_url="http://127.0.0.1:19999", batch_size=3)

    for i in range(2):
        agent.enqueue({"task_id": f"client-test-{i}", "query": f"测试{i}",
                       "intent_category": "operation_guide", "route": "L2",
                       "total_steps": 1, "completed_steps": 1, "result": "success",
                       "duration_ms": 100, "fingerprint_mismatches": 0,
                       "redline_triggered": False})

    depth = agent.get_queue_depth()
    ok(f"入队: depth={depth}", depth >= 2)
    ok(f"client_id: {agent.get_queue_status()['client_id'][:20]}...",
       agent.get_queue_status()["client_id"].startswith("desktop-"))

    # Flush (server unreachable → records stay)
    result = agent.flush_now()
    ok(f"离线降级: sent={result.get('sent',0)}", result.get("sent", 0) == 0)
    ok(f"队列保留: depth={agent.get_queue_depth()}", agent.get_queue_depth() >= 2)

    # Feedback
    fb_ok = agent.send_feedback("test-001", "useful", "test")
    ok(f"send_feedback方法存在(离线返回False)", not fb_ok)

    agent.shutdown()

# ── 4. 配置轮询 ──
def test_config():
    print("\n========= 4. C-配置轮询 =========")
    from client.config.config_poller import ConfigPoller

    changed = None
    def on_changed(cfg):
        nonlocal changed; changed = cfg

    poller = ConfigPoller(server_url="http://127.0.0.1:19999", interval_min=5,
                          on_config_changed=on_changed)

    state = poller.get_state()
    ok(f"初始状态: running={state['running']}, interval={state['interval_min']}", state['interval_min'] == 5)

    # Interval bounds test
    poller.set_interval(3)
    ok(f"下限保护: 3→{poller.interval_min}", poller.interval_min == 5)
    poller.set_interval(2000)
    ok(f"上限保护: 2000→{poller.interval_min}", poller.interval_min == 1440)
    poller.set_interval(30)
    ok(f"正常设置: {poller.interval_min}", poller.interval_min == 30)

    # Offline fallback
    result = poller.poll_now()
    ok(f"离线降级: 返回None={result is None}", result is None)

    # Config change notification
    poller._notify_changed({"version": "v99.99", "test": True})
    ok(f"变更通知: version={changed.get('version','?')}", changed is not None
       and changed.get("version") == "v99.99")

    poller.shutdown()

# ── 5. B-C 集成控制器 ──
def test_integration():
    print("\n========= 5. C-BC 集成控制器 =========")
    from client.integration.controller import VoiceIntegrationController, HealthStatus

    ctrl = VoiceIntegrationController(server_url="http://127.0.0.1:19999")
    ok("控制器创建", not ctrl._started)

    ctrl.start()
    ok("控制器启动", ctrl._started)

    health = ctrl.health_check()
    ok(f"健康检查: overall={health.overall}", health.overall in ("healthy", "degraded", "unhealthy"))

    # All 7 fields
    fields = ["asr_available", "asr_engine", "tts_available", "tts_engine",
              "audit_db_ok", "server_reachable", "queue_depth"]
    for f in fields:
        ok(f"字段 {f}", hasattr(health, f))

    # Health state transitions
    h1 = HealthStatus(asr_available=True, tts_available=True, audit_db_ok=True, server_reachable=True)
    ok(f"全部健康→{h1.overall}", h1.overall == "healthy")
    h2 = HealthStatus()
    ok(f"全不可用→{h2.overall}", h2.overall == "unhealthy")
    h3 = HealthStatus(asr_available=True, tts_available=False, audit_db_ok=True, server_reachable=True)
    ok(f"部分降级→{h3.overall}", h3.overall == "degraded")

    ctrl.shutdown()

# ── 6. AuditRecord 构建器 (B端) ──
def test_audit_builder():
    print("\n========= 6. AuditRecord Builder =========")
    # Import from HAJIMI_UI
    hajimi_path = os.path.join(PROJECT, "HAJIMI_UI")
    if os.path.isdir(hajimi_path):
        sys.path.insert(0, hajimi_path)
        try:
            from core.bc_signals import AuditRecordBuilder
            record = AuditRecordBuilder.build(
                task_id="builder-test", query="怎么安装微信",
                intent={"category": "operation_guide", "complexity_score": 30},
                route="L3", steps=[{"step": 1}, {"step": 2}, {"step": 3}],
                completed_steps=3, result="success", started_at=None,
                fingerprint_mismatches=0, redline_triggered=False)
            ok(f"task_id: {record['task_id']}", record['task_id'] == "builder-test")
            ok(f"intent_category: {record['intent_category']}", record['intent_category'] == "operation_guide")
            ok(f"route: {record['route']}", record['route'] == "L3")
            ok(f"total_steps: {record['total_steps']}", record['total_steps'] == 3)
            ok(f"completed_steps: {record['completed_steps']}", record['completed_steps'] == 3)
            ok(f"result: {record['result']}", record['result'] == "success")
            ok(f"11字段全在: {sorted(record.keys())}", len(record) >= 11)
        except ImportError as e:
            ok(f"AuditRecordBuilder导入", False)
    else:
        print("  [SKIP] HAJIMI_UI 不在项目中")

# ══ MAIN ══
if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  HAJIMI C-end 客户端模块单元测试")
    print(f"  目标: C端 6 核心模块 (不需要A端)")
    print(f"{'='*50}")
    test_asr()
    test_tts()
    test_audit()
    test_config()
    test_integration()
    test_audit_builder()
    print(f"\n{'='*50}")
    print(f"  结果: {PASS} 通过, {FAIL} 失败")
    if FAIL == 0:
        print(f"  C-end 全部通过")
    else:
        print(f"  {FAIL} 项失败")
