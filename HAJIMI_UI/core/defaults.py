"""Shared default URLs/ports for B-end and L5 Sidecar (single source of truth).

Bat scripts cannot import this module; keep scripts\\start_*.bat in sync manually.
L4 指引模式与 OmniParser 已于 2026-09 移除：唯一后端是 server_A L5 Sidecar (:8011)。
"""

DEFAULT_L5_HOST = "127.0.0.1"
DEFAULT_L5_PORT = 8011
DEFAULT_L5_URL = f"http://{DEFAULT_L5_HOST}:{DEFAULT_L5_PORT}"
DEFAULT_DEMO_KEY = "hajimi-demo-2026"

DEFAULT_VOICE_SETTINGS = {
    "tts_enabled": True,
    "tts_speed": 0.85,
    "tts_engine": "pyttsx3",
    "asr_enabled": True,
    "asr_engine": "vosk",
    "asr_language": "zh-CN",
    "microphone_index": None,
    "vosk_model_path": "models/vosk-model-small-cn-0.22",
    "asr_silence_sec": 5.0,
    "asr_start_timeout_sec": 10.0,
    "config_pull_interval_min": 30,
}

# L5 文本规划 LLM 默认（DeepSeek 官方；模型 key 存 server_A/server/.env）
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
