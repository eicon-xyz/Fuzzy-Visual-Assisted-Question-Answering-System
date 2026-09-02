"""B 端运行时配置（环境变量 → 模块属性）。

仅剩 L5 自动执行模式：后端 = server_A Sidecar (:8011)。
旧 A 端 (:8010)、OmniParser、Mock 演示、内网部署模式已随 L4 指引模式移除。
"""
import os

from core.defaults import (
    DEFAULT_DEMO_KEY,
    DEFAULT_L5_HOST,
    DEFAULT_L5_PORT,
)


def _build_default_l5_api_url() -> str:
    host = os.environ.get("L5_API_HOST", DEFAULT_L5_HOST)
    port = os.environ.get("L5_API_PORT", str(DEFAULT_L5_PORT))
    return f"http://{host}:{port}"


L5_API_URL = os.environ.get("L5_API_URL", _build_default_l5_api_url())
L5_DEFAULT_PORT = int(os.environ.get("L5_API_PORT", str(DEFAULT_L5_PORT)))
# server_A Sidecar 根目录（空则 core.paths.resolve_l5_root → ../server_A）
HAJIMI_L5_ROOT = os.environ.get("HAJIMI_L5_ROOT", "").strip()
AUTO_LAUNCH_L5 = os.environ.get("HAJIMI_AUTO_LAUNCH_L5", "1").lower() not in (
    "0",
    "false",
    "no",
)
L5_START_HINT = (
    f"scripts\\start_l5_sidecar.bat  (server_A L5 Sidecar default :{DEFAULT_L5_PORT})"
)
L5_TOOL_SSE = os.environ.get("HAJIMI_L5_TOOL_SSE", "0").lower() in (
    "1",
    "true",
    "yes",
)

DEMO_KEY = os.environ.get("HAJIMI_DEMO_KEY", DEFAULT_DEMO_KEY)
API_TIMEOUT = int(os.environ.get("HAJIMI_API_TIMEOUT", "30"))
HEALTH_TIMEOUT = int(os.environ.get("HAJIMI_HEALTH_TIMEOUT", "2"))
# L5 执行任务可能很长：SSE/提交超时独立配置
EXECUTE_TIMEOUT = int(os.environ.get("HAJIMI_EXECUTE_TIMEOUT", "360"))

FRAMED_WINDOW = os.environ.get("HAJIMI_FRAMED", "").lower() in ("1", "true", "yes")
USE_NATIVE_UI = os.environ.get("HAJIMI_NATIVE_UI", "1").lower() not in ("0", "false", "no")

MEDIUM_WIDTH = 400
MEDIUM_HEIGHT = 520
COMPACT_WIDTH = 320
COMPACT_HEIGHT = 52
MODE_PILLS_MIN_WIDTH = 700

# 启动时 L5 Sidecar health 探测：避免 Sidecar 仍在初始化就报「未启动」
STARTUP_HEALTH_DELAY_MS = int(os.environ.get("HAJIMI_STARTUP_HEALTH_DELAY_MS", "3000"))
STARTUP_HEALTH_RETRY_MS = int(os.environ.get("HAJIMI_STARTUP_HEALTH_RETRY_MS", "4000"))
STARTUP_HEALTH_MAX_RETRIES = int(os.environ.get("HAJIMI_STARTUP_HEALTH_MAX_RETRIES", "6"))

# 运行中后台重连：未连接 10s / 已连接 60s 保活
BACKEND_POLL_DISCONNECTED_MS = int(
    os.environ.get(
        "HAJIMI_BACKEND_POLL_MS",
        os.environ.get("HAJIMI_BACKEND_POLL_DISCONNECTED_MS", "10000"),
    )
)
BACKEND_POLL_CONNECTED_MS = int(os.environ.get("HAJIMI_BACKEND_POLL_CONNECTED_MS", "60000"))

# 关闭 B 端窗口 / 托盘退出时是否按端口停止 L5 Sidecar
STOP_SERVICES_ON_EXIT = os.environ.get("HAJIMI_STOP_SERVICES_ON_EXIT", "1").lower() not in (
    "0",
    "false",
    "no",
)


def reload_from_env() -> None:
    """从 os.environ 刷新模块级配置（user_settings.apply 后调用）。"""
    global L5_API_URL, L5_DEFAULT_PORT, HAJIMI_L5_ROOT
    global AUTO_LAUNCH_L5, L5_START_HINT, L5_TOOL_SSE
    global DEMO_KEY, API_TIMEOUT, HEALTH_TIMEOUT, EXECUTE_TIMEOUT

    l5_host = os.environ.get("L5_API_HOST", DEFAULT_L5_HOST)
    l5_port = os.environ.get("L5_API_PORT", str(DEFAULT_L5_PORT))
    L5_API_URL = os.environ.get("L5_API_URL", f"http://{l5_host}:{l5_port}")
    L5_DEFAULT_PORT = int(l5_port)
    HAJIMI_L5_ROOT = os.environ.get("HAJIMI_L5_ROOT", "").strip()
    AUTO_LAUNCH_L5 = os.environ.get("HAJIMI_AUTO_LAUNCH_L5", "1").lower() not in (
        "0",
        "false",
        "no",
    )
    L5_START_HINT = (
        f"scripts\\start_l5_sidecar.bat  (server_A L5 Sidecar default :{L5_DEFAULT_PORT})"
    )
    L5_TOOL_SSE = os.environ.get("HAJIMI_L5_TOOL_SSE", "0").lower() in (
        "1",
        "true",
        "yes",
    )
    DEMO_KEY = os.environ.get("HAJIMI_DEMO_KEY", DEFAULT_DEMO_KEY)
    API_TIMEOUT = int(os.environ.get("HAJIMI_API_TIMEOUT", "30"))
    HEALTH_TIMEOUT = int(os.environ.get("HAJIMI_HEALTH_TIMEOUT", "2"))
    EXECUTE_TIMEOUT = int(os.environ.get("HAJIMI_EXECUTE_TIMEOUT", "360"))
