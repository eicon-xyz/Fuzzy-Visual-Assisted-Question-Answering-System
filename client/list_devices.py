#!/usr/bin/env python3
"""
HAJIMI — 音频设备列表工具
============================
列出所有可用的麦克风和扬声器设备，帮助配置 ASR/TTS。

用法::

    python client/list_devices.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def list_microphones():
    """通过 PyAudio 列出麦克风"""
    print("═" * 60)
    print("  🎤 麦克风设备 (ASR)")
    print("═" * 60)

    try:
        import pyaudio
        p = pyaudio.PyAudio()
        count = p.get_device_count()
        found = 0
        default_input = p.get_default_input_device_info()
        default_index = default_input["index"] if default_input else None

        for i in range(count):
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                found += 1
                is_default = " ★ 默认" if i == default_index else ""
                print(f"\n  设备 #{i}{is_default}")
                print(f"    名称: {info.get('name', 'Unknown')}")
                print(f"    输入通道: {info.get('maxInputChannels')}")
                print(f"    默认采样率: {int(info.get('defaultSampleRate', 0))} Hz")

        p.terminate()

        if found == 0:
            print("  ⚠ 未检测到麦克风设备")
        else:
            print(f"\n  共 {found} 个麦克风设备可用")
            print(f"  ASRClient(microphone_index={default_index})  # 默认设备")

    except ImportError:
        print("  ⚠ PyAudio 未安装 — 无法枚举设备")
        print("    安装: pip install pyaudio")
    except Exception as e:
        print(f"  ❌ 枚举失败: {e}")


def list_speakers():
    """通过 pyttsx3 列出 TTS 语音"""
    print()
    print("═" * 60)
    print("  🔊 TTS 语音包")
    print("═" * 60)

    from client.voice.tts_engine import TTSEngine
    voices = TTSEngine.list_voices()

    if not voices:
        print("  ⚠ 未检测到 TTS 语音包")
        return

    for i, v in enumerate(voices):
        lang_str = ", ".join([str(l) for l in v.get("languages", []) if l])
        is_zh = any(
            "zh" in str(l).lower() or "chinese" in v.get("name", "").lower()
            for l in v.get("languages", [])
        )
        marker = " ★ 中文" if is_zh else ""
        print(f"\n  语音 #{i}{marker}")
        print(f"    ID: {v['id']}")
        print(f"    名称: {v['name']}")
        print(f"    语言: {lang_str or '未知'}")
        print(f"    性别: {v.get('gender', 'unknown')}")

    print(f"\n  共 {len(voices)} 个语音包可用")
    print(f"  TTSEngine(voice_id='<ID>')  # 指定语音")


def list_output_devices():
    """通过 PyAudio 列出扬声器"""
    print()
    print("═" * 60)
    print("  🔊 音频输出设备")
    print("═" * 60)

    try:
        import pyaudio
        p = pyaudio.PyAudio()
        count = p.get_device_count()
        found = 0
        default_output = p.get_default_output_device_info()
        default_index = default_output["index"] if default_output else None

        for i in range(count):
            info = p.get_device_info_by_index(i)
            if info.get("maxOutputChannels", 0) > 0:
                found += 1
                is_default = " ★ 默认" if i == default_index else ""
                print(f"\n  设备 #{i}{is_default}")
                print(f"    名称: {info.get('name', 'Unknown')}")
                print(f"    输出通道: {info.get('maxOutputChannels')}")
                print(f"    默认采样率: {int(info.get('defaultSampleRate', 0))} Hz")

        p.terminate()

        if found > 0:
            print(f"\n  共 {found} 个输出设备可用")
            print(f"  pyttsx3 通常使用系统默认输出设备")

    except ImportError:
        print("  ⚠ PyAudio 未安装")


def main():
    print()
    print("╔" + "═" * 58 + "╗")
    print("║  HAJIMI 音频设备列表                                     ║")
    print("╚" + "═" * 58 + "╝")

    list_microphones()
    list_speakers()
    list_output_devices()

    print()
    print("═" * 60)
    print("  快速配置示例")
    print("═" * 60)
    print("""
  # 使用默认设备
  from client.voice.asr_client import ASRClient
  asr = ASRClient()

  # 指定麦克风设备（从上面列表中选择 index）
  asr = ASRClient(microphone_index=1)

  # 列出所有麦克风
  for mic in ASRClient.list_microphones():
      print(mic)

  # 指定 TTS 语音包
  from client.voice.tts_engine import TTSEngine
  for v in TTSEngine.list_voices():
      print(v)

  tts = TTSEngine(voice_id=v['id'])  # 指定某个语音 ID
""")


if __name__ == "__main__":
    main()
