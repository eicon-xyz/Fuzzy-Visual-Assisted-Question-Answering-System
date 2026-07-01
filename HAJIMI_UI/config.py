import os

_DEFAULT_PORT = os.environ.get("HAJIMI_PORT", "8010")
_DEFAULT_HOST = os.environ.get("HAJIMI_HOST", "127.0.0.1")
_DEFAULT_API_URL = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}"

API_BASE_URL = os.environ.get("HAJIMI_API_URL", _DEFAULT_API_URL)
DEMO_KEY = os.environ.get("HAJIMI_DEMO_KEY", "hajimi-demo-2026")
USE_MOCK_ONLY = os.environ.get("HAJIMI_MOCK_ONLY", "").lower() in ("1", "true", "yes")
ALLOW_MOCK_FALLBACK = os.environ.get("HAJIMI_MOCK_FALLBACK", "").lower() in (
    "1",
    "true",
    "yes",
)
API_TIMEOUT = int(os.environ.get("HAJIMI_API_TIMEOUT", "30"))
# CPU 本地 OmniParser 全屏检测约 2–4 分钟，留余量避免 B 端先超时
INSPECT_TIMEOUT = int(os.environ.get("HAJIMI_INSPECT_TIMEOUT", "360"))
PROCESS_TIMEOUT = int(os.environ.get("HAJIMI_PROCESS_TIMEOUT", "360"))
HEALTH_TIMEOUT = int(os.environ.get("HAJIMI_HEALTH_TIMEOUT", "2"))

FRAMED_WINDOW = os.environ.get("HAJIMI_FRAMED", "").lower() in ("1", "true", "yes")
USE_NATIVE_UI = os.environ.get("HAJIMI_NATIVE_UI", "1").lower() not in ("0", "false", "no")

MEDIUM_WIDTH = 370
MEDIUM_HEIGHT = 540
COMPACT_WIDTH = 280
COMPACT_HEIGHT = 52
MODE_PILLS_MIN_WIDTH = 400

# 启动时 A 端 health 探测：避免 A 端/OmniParser 仍在初始化就报「未启动」
STARTUP_HEALTH_DELAY_MS = int(os.environ.get("HAJIMI_STARTUP_HEALTH_DELAY_MS", "12000"))
STARTUP_HEALTH_RETRY_MS = int(os.environ.get("HAJIMI_STARTUP_HEALTH_RETRY_MS", "4000"))
STARTUP_HEALTH_MAX_RETRIES = int(os.environ.get("HAJIMI_STARTUP_HEALTH_MAX_RETRIES", "6"))

SERVER_DEFAULT_PORT = int(_DEFAULT_PORT)
SERVER_START_HINT = (
    f"scripts\\start_server.bat  (default port {SERVER_DEFAULT_PORT}, "
    f"or: python -m uvicorn server.main:app --host 127.0.0.1 --port {SERVER_DEFAULT_PORT})"
)
START_ALL_HINT = "scripts\\start_all.bat  （或设置页「启动 OmniParser + A 端」）"
# 关闭 B 端窗口 / 托盘退出时是否按端口停止 A 端与 OmniParser
STOP_SERVICES_ON_EXIT = os.environ.get("HAJIMI_STOP_SERVICES_ON_EXIT", "1").lower() not in (
    "0",
    "false",
    "no",
)
