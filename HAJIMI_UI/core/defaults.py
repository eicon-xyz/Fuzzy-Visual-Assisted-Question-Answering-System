"""Shared default URLs/ports for B-end and A-end (single source of truth).

Bat scripts cannot import this module; keep scripts\\start_*.bat in sync manually.
See docs/P1-可移植性改动与使用指南.md.
"""

DEFAULT_A_HOST = "127.0.0.1"
DEFAULT_A_PORT = 8010
DEFAULT_A_URL = f"http://{DEFAULT_A_HOST}:{DEFAULT_A_PORT}"
DEFAULT_L5_HOST = "127.0.0.1"
DEFAULT_L5_PORT = 8011
DEFAULT_L5_URL = f"http://{DEFAULT_L5_HOST}:{DEFAULT_L5_PORT}"
DEFAULT_OMNI_LOCAL_URL = "http://127.0.0.1:8002"
DEFAULT_OMNI_GPU_API_URL = "http://127.0.0.1:9800"
DEFAULT_OMNI_GPU_URL = ""  # campus GPU: set in server/.env or settings page
DEFAULT_DEPLOYMENT_MODE = "gpu_api"
DEFAULT_DEMO_KEY = "hajimi-demo-2026"

DEFAULT_VOICE_SETTINGS = {
    "tts_enabled": True,
    "tts_speed": 0.85,
    "tts_engine": "pyttsx3",
    "asr_enabled": True,
    "asr_engine": "vosk",
    "asr_language": "zh-CN",
    "config_pull_interval_min": 30,
}

# LLM 识图默认：GPT-4o（OpenAI 兼容）；DeepSeek 见 server/.env DEEPSEEK_*
DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL = "gpt-4o"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
