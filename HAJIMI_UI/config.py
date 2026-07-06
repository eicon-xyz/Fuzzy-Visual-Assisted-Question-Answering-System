import os

from core.defaults import DEFAULT_A_HOST, DEFAULT_A_PORT, DEFAULT_DEMO_KEY, DEFAULT_DEPLOYMENT_MODE

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
HEALTH_TIMEOUT = int(os.environ.get("HAJIMI_HEALTH_TIMEOUT", "2"))

FRAMED_WINDOW = os.environ.get("HAJIMI_FRAMED", "").lower() in ("1", "true", "yes")
USE_NATIVE_UI = os.environ.get("HAJIMI_NATIVE_UI", "1").lower() not in ("0", "false", "no")

MEDIUM_WIDTH = 400
MEDIUM_HEIGHT = 520
COMPACT_WIDTH = 320
COMPACT_HEIGHT = 52
MODE_PILLS_MIN_WIDTH = 700

# 启动时 A 端 health 探测：避免 A 端/OmniParser 仍在初始化就报「未启动」
STARTUP_HEALTH_DELAY_MS = int(os.environ.get("HAJIMI_STARTUP_HEALTH_DELAY_MS", "12000"))
STARTUP_HEALTH_RETRY_MS = int(os.environ.get("HAJIMI_STARTUP_HEALTH_RETRY_MS", "4000"))
STARTUP_HEALTH_MAX_RETRIES = int(os.environ.get("HAJIMI_STARTUP_HEALTH_MAX_RETRIES", "6"))

SERVER_DEFAULT_PORT = int(_DEFAULT_PORT)
SERVER_START_HINT = (
    f"scripts\\start_server.bat  (default port {SERVER_DEFAULT_PORT}, "
    f"or: python -m uvicorn server.main:app --host 127.0.0.1 --port {SERVER_DEFAULT_PORT})"
)
L4_START_HINT = (
    f"scripts\\start_l4_demo.bat  (L4 仅需 A 端 :{SERVER_DEFAULT_PORT} + LLM，无需 OmniParser)"
)
START_ALL_HINT = "scripts\\start_all.bat  （或设置页「启动 OmniParser + A 端」）"
# 关闭 B 端窗口 / 托盘退出时是否按端口停止 A 端与 OmniParser
STOP_SERVICES_ON_EXIT = os.environ.get("HAJIMI_STOP_SERVICES_ON_EXIT", "1").lower() not in (
    "0",
    "false",
    "no",
)


def _default_inspect_timeout() -> int:
    mode = os.environ.get("HAJIMI_DEPLOYMENT_MODE", DEFAULT_DEPLOYMENT_MODE)
    if mode in ("gpu_api", "intranet"):
        return 180
    return 360


DEPLOYMENT_MODE = os.environ.get("HAJIMI_DEPLOYMENT_MODE", DEFAULT_DEPLOYMENT_MODE)
if "HAJIMI_INSPECT_TIMEOUT" in os.environ:
    INSPECT_TIMEOUT = int(os.environ["HAJIMI_INSPECT_TIMEOUT"])
else:
    INSPECT_TIMEOUT = _default_inspect_timeout()
if "HAJIMI_PROCESS_TIMEOUT" in os.environ:
    PROCESS_TIMEOUT = int(os.environ["HAJIMI_PROCESS_TIMEOUT"])
else:
    PROCESS_TIMEOUT = _default_inspect_timeout()

SCREENSHOT_MAX_SIDE = int(os.environ.get("HAJIMI_SCREENSHOT_MAX_SIDE", "720"))
L4_UPLOAD_MAX_SIDE = int(os.environ.get("HAJIMI_L4_UPLOAD_MAX_SIDE", "1280"))
INSPECT_MAX_SIDE = int(os.environ.get("HAJIMI_INSPECT_MAX_SIDE", "960"))


def reload_from_env() -> None:
    """从 os.environ 刷新模块级配置（user_settings.apply 后调用）。"""
    global API_BASE_URL, DEMO_KEY, USE_MOCK_ONLY, ALLOW_MOCK_FALLBACK
    global API_TIMEOUT, INSPECT_TIMEOUT, PROCESS_TIMEOUT, HEALTH_TIMEOUT
    global DEPLOYMENT_MODE, SERVER_DEFAULT_PORT, SERVER_START_HINT, L4_START_HINT
    global SCREENSHOT_MAX_SIDE, INSPECT_MAX_SIDE, L4_UPLOAD_MAX_SIDE, L4_UPLOAD_MAX_SIDE

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
    if "HAJIMI_INSPECT_TIMEOUT" in os.environ:
        INSPECT_TIMEOUT = int(os.environ["HAJIMI_INSPECT_TIMEOUT"])
    else:
        INSPECT_TIMEOUT = _default_inspect_timeout()
    if "HAJIMI_PROCESS_TIMEOUT" in os.environ:
        PROCESS_TIMEOUT = int(os.environ["HAJIMI_PROCESS_TIMEOUT"])
    else:
        PROCESS_TIMEOUT = _default_inspect_timeout()
    HEALTH_TIMEOUT = int(os.environ.get("HAJIMI_HEALTH_TIMEOUT", "2"))
    DEPLOYMENT_MODE = os.environ.get("HAJIMI_DEPLOYMENT_MODE", DEFAULT_DEPLOYMENT_MODE)

    port = os.environ.get("HAJIMI_PORT", str(SERVER_DEFAULT_PORT))
    SERVER_DEFAULT_PORT = int(port)
    SERVER_START_HINT = (
        f"scripts\\start_server.bat  (default port {SERVER_DEFAULT_PORT}, "
        f"or: python -m uvicorn server.main:app --host 127.0.0.1 --port {SERVER_DEFAULT_PORT})"
    )
    L4_START_HINT = (
        f"scripts\\start_l4_demo.bat  (L4 仅需 A 端 :{SERVER_DEFAULT_PORT} + LLM，无需 OmniParser)"
    )
    SCREENSHOT_MAX_SIDE = int(os.environ.get("HAJIMI_SCREENSHOT_MAX_SIDE", "720"))
    L4_UPLOAD_MAX_SIDE = int(os.environ.get("HAJIMI_L4_UPLOAD_MAX_SIDE", "1280"))
    INSPECT_MAX_SIDE = int(os.environ.get("HAJIMI_INSPECT_MAX_SIDE", "960"))
