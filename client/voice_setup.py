"""
HAJIMI Client — Day 1 语音模块验证脚本
=========================================
分别测试 TTS（语音合成）和 ASR（语音识别），互不干扰。

用法::

    python client/voice_setup.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


# ═══════════════════════════════════════════════
#  设备配置
# ═══════════════════════════════════════════════
MIC_INDEX = 2          # Air5 麦克风
ASR_ENGINE = "google"  # "vosk"(离线) / "google"(在线) / "mock"
VOSK_MODEL = "models/vosk-model-small-cn-0.22"


def test_tts():
    """测试 TTS：播放三条语音"""
    print("=" * 50)
    print("  1. TTS 语音合成测试")
    print("=" * 50)

    import pyttsx3
    engine = pyttsx3.init()

    voices = engine.getProperty("voices")
    zh = [v for v in voices if "zh" in str(getattr(v, "languages", []))]
    if zh:
        engine.setProperty("voice", zh[0].id)
        print(f"  语音: {zh[0].name}")

    texts = [
        "你好，我是哈吉米智能桌面助手",
        "请点击桌面上的浏览器图标",
        "测试完成，语音模块工作正常",
    ]
    for i, text in enumerate(texts, 1):
        print(f"  [{i}/3] {text}")
        engine.say(text)
    engine.runAndWait()          # 全部 say 完之后一次性 runAndWait
    print("  TTS 测试通过\n")


def test_asr():
    """测试 ASR：录音并识别"""
    print("=" * 50)
    print("  2. ASR 语音识别测试")
    print("=" * 50)

    from client.voice.asr_client import ASRClient, ASREngine

    asr = ASRClient(
        microphone_index=MIC_INDEX,
        engine=ASR_ENGINE,
        vosk_model_path=VOSK_MODEL,
    )

    status = asr.engine_status
    print(f"  引擎: {status['active_engine']}")
    print(f"  Vosk 模型: {'就绪' if status['vosk_available'] else '未下载'}")

    if status["active_engine"] == ASREngine.MOCK:
        print("  ⚠ 无可用的语音引擎，跳过录音测试\n")
        return

    input("  按 Enter 开始录音，说话后等待自动结束...")
    print("  🎤 录音中 (5秒)...")
    asr.start_recording()
    time.sleep(5)
    result = asr.stop_and_transcribe()

    if result.success:
        print(f"  识别结果: {result.transcript}")
        print(f"  引擎: {result.engine}")
    else:
        print(f"  识别失败: {result.error}")

    print("  ASR 测试完成\n")


def test_audit():
    """测试审计代理：写入 + 脱敏"""
    print("=" * 50)
    print("  3. 审计代理测试")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent, desensitize_text

    # 每次用独立测试库，避免累积
    import tempfile
    agent = AuditAgent(db_path=os.path.join(tempfile.gettempdir(), "hajimi_test_audit.db"))

    # 写入几条测试记录
    for i in range(2):
        agent.enqueue({
            "task_id": f"day1-test-{i}",
            "query": f"测试操作 {i}",
            "intent_category": "operation_guide",
            "complexity_score": 30,
            "route": "L2",
            "total_steps": 3,
            "completed_steps": 3,
            "result": "success",
            "duration_ms": 5000,
            "fingerprint_mismatches": 0,
            "redline_triggered": False,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        })

    depth = agent.get_queue_depth()
    print(f"  队列深度: {depth}")

    # 脱敏测试
    result = desensitize_text("密码=abc123 手机号 13912345678")
    print(f"  脱敏测试: {result}")

    agent.shutdown()
    print("  审计代理测试通过\n")


if __name__ == "__main__":
    print()
    print("  HAJIMI Day 1 — 语音模块验证")
    print()

    test_tts()
    test_asr()
    test_audit()

    print("=" * 50)
    print("  Day 1 验证完成")
    print("=" * 50)
