import os

from core.defaults import DEFAULT_A_HOST, DEFAULT_A_PORT, DEFAULT_DEMO_KEY

_DEFAULT_PORT = os.environ.get("HAJIMI_PORT", str(DEFAULT_A_PORT))
_DEFAULT_HOST = os.environ.get("HAJIMI_HOST", DEFAULT_A_HOST)


def _build_default_api_url() -> str:
    port = os.environ.get("HAJIMI_PORT", str(DEFAULT_A_PORT))
    host = os.environ.get("HAJIMI_HOST", DEFAULT_A_HOST)
    return f"http://{host}:{port}"


_DEFAULT_API_URL = _build_default_api_url()

API_BASE_URL = os.environ.get("HAJIMI_API_URL", _DEFAULT_API_URL)
DEMO_KEY = os.environ.get("HAJIMI_DEMO_KEY", DEFAULT_DEMO_KEY)
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
AUTO_LAUNCH_A_END = os.environ.get("HAJIMI_AUTO_LAUNCH_A_END", "1").lower() not in (
    "0",
    "false",
    "no",
)

FRAMED_WINDOW = os.environ.get("HAJIMI_FRAMED", "").lower() in ("1", "true", "yes")
USE_NATIVE_UI = os.environ.get("HAJIMI_NATIVE_UI", "1").lower() not in ("0", "false", "no")

MEDIUM_WIDTH = 400
MEDIUM_HEIGHT = 520
COMPACT_WIDTH = 320
COMPACT_HEIGHT = 52
MODE_PILLS_MIN_WIDTH = 700

# 启动时 A 端 health 探测：避免 A 端/OmniParser 仍在初始化就报「未启动」
STARTUP_HEALTH_DELAY_MS = int(os.environ.get("HAJIMI_STARTUP_HEALTH_DELAY_MS", "15000"))
STARTUP_HEALTH_RETRY_MS = int(os.environ.get("HAJIMI_STARTUP_HEALTH_RETRY_MS", "5000"))
STARTUP_HEALTH_MAX_RETRIES = int(os.environ.get("HAJIMI_STARTUP_HEALTH_MAX_RETRIES", "12"))

SERVER_DEFAULT_PORT = int(_DEFAULT_PORT)
SERVER_START_HINT = (
    f"scripts\\start_server.bat  (default port {SERVER_DEFAULT_PORT}, "
    f"or: python -m uvicorn server.main:app --host 127.0.0.1 --port {SERVER_DEFAULT_PORT})"
)
START_ALL_HINT = "scripts\\start_all.bat（或设置页「启动 A 端」）"
# 关闭 B 端窗口 / 托盘退出时是否按端口停止 A 端与 OmniParser
STOP_SERVICES_ON_EXIT = os.environ.get("HAJIMI_STOP_SERVICES_ON_EXIT", "1").lower() not in (
    "0",
    "false",
    "no",
)

DEPLOYMENT_MODE = os.environ.get("HAJIMI_DEPLOYMENT_MODE", "local")


def reload_from_env() -> None:
    """从 os.environ 刷新模块级配置（user_settings.apply 后调用）。"""
    global API_BASE_URL, DEMO_KEY, USE_MOCK_ONLY, ALLOW_MOCK_FALLBACK
    global API_TIMEOUT, INSPECT_TIMEOUT, PROCESS_TIMEOUT, HEALTH_TIMEOUT
    global DEPLOYMENT_MODE, SERVER_DEFAULT_PORT, SERVER_START_HINT, START_ALL_HINT, AUTO_LAUNCH_A_END

    port = os.environ.get("HAJIMI_PORT", str(DEFAULT_A_PORT))
    host = os.environ.get("HAJIMI_HOST", DEFAULT_A_HOST)
    default_url = f"http://{host}:{port}"
    API_BASE_URL = os.environ.get("HAJIMI_API_URL", default_url)
    DEMO_KEY = os.environ.get("HAJIMI_DEMO_KEY", DEFAULT_DEMO_KEY)
    USE_MOCK_ONLY = os.environ.get("HAJIMI_MOCK_ONLY", "").lower() in ("1", "true", "yes")
    ALLOW_MOCK_FALLBACK = os.environ.get("HAJIMI_MOCK_FALLBACK", "").lower() in (
        "1",
        "true",
        "yes",
    )
    API_TIMEOUT = int(os.environ.get("HAJIMI_API_TIMEOUT", "30"))
    INSPECT_TIMEOUT = int(os.environ.get("HAJIMI_INSPECT_TIMEOUT", "360"))
    PROCESS_TIMEOUT = int(os.environ.get("HAJIMI_PROCESS_TIMEOUT", "360"))
    HEALTH_TIMEOUT = int(os.environ.get("HAJIMI_HEALTH_TIMEOUT", "2"))
    DEPLOYMENT_MODE = os.environ.get("HAJIMI_DEPLOYMENT_MODE", "local")
    AUTO_LAUNCH_A_END = os.environ.get("HAJIMI_AUTO_LAUNCH_A_END", "1").lower() not in (
        "0",
        "false",
        "no",
    )

    port = os.environ.get("HAJIMI_PORT", str(SERVER_DEFAULT_PORT))
    SERVER_DEFAULT_PORT = int(port)
    SERVER_START_HINT = (
        f"scripts\\start_server.bat  (default port {SERVER_DEFAULT_PORT}, "
        f"or: python -m uvicorn server.main:app --host 127.0.0.1 --port {SERVER_DEFAULT_PORT})"
    )
    START_ALL_HINT = "scripts\\start_all.bat（或设置页「启动 A 端」）"
