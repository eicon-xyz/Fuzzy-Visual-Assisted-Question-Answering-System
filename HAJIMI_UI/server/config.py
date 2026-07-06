"""
HAJIMI Server Demo 配置文件
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from core.defaults import (
    DEFAULT_A_PORT,
    DEFAULT_DEMO_KEY,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_OMNI_LOCAL_URL,
)

SERVER_DIR = Path(__file__).resolve().parent
ENV_PATH = SERVER_DIR / ".env"
CONFIG_SOURCE = "server/.env"


def _default_omni_timeout(url: str) -> str:
    if ":9800" in (url or ""):
        return "120"
    return "360"


def _load_env(override: bool = False) -> None:
    if ENV_PATH.is_file():
        load_dotenv(ENV_PATH, override=override)
    else:
        load_dotenv(override=override)


_load_env()

_OMNI_URL = os.getenv("OMNIPARSER_URL", DEFAULT_OMNI_LOCAL_URL)


class Config:
    """Demo 阶段配置（实例属性由 reload_settings 刷新）。"""

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        _load_env(override=True)
        omni_url = os.getenv("OMNIPARSER_URL", DEFAULT_OMNI_LOCAL_URL)
        default_timeout = _default_omni_timeout(omni_url)

        self.HOST = os.getenv("HAJIMI_HOST", "0.0.0.0")
        self.PORT = int(os.getenv("HAJIMI_PORT", str(DEFAULT_A_PORT)))
        self.DEBUG = os.getenv("HAJIMI_DEBUG", "true").lower() == "true"
        self.DEMO_KEY = os.getenv("HAJIMI_DEMO_KEY", DEFAULT_DEMO_KEY)

        self.LLM_API_KEY = os.getenv("LLM_API_KEY", "")
        self.LLM_BASE_URL = os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL)
        self.LLM_MODEL = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
        self.LLM_WIRE_API = os.getenv("LLM_WIRE_API", "").lower()
        self.LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
        self.LLM_ATTEMPT_TIMEOUT = int(os.getenv("LLM_ATTEMPT_TIMEOUT", "15"))
        self.LLM_VISION_ATTEMPT_TIMEOUT = int(
            os.getenv("LLM_VISION_ATTEMPT_TIMEOUT", "45")
        )
        self.LLM_SPEED_MODE = os.getenv("LLM_SPEED_MODE", "fast").lower()
        self.LLM_FAST_TIMEOUT = int(os.getenv("LLM_FAST_TIMEOUT", "15"))
        self.OMNIPARSER_FAST_MAX_SIDE = int(
            os.getenv("OMNIPARSER_FAST_MAX_SIDE", "720")
        )
        self.OMNIPARSER_FAST_TIMEOUT = int(
            os.getenv("OMNIPARSER_FAST_TIMEOUT", "30")
        )

        self.DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
        self.DEEPSEEK_BASE_URL = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "30"))

        self.OMNIPARSER_URL = omni_url
        self.OMNIPARSER_LOCAL_URL = os.getenv("OMNIPARSER_LOCAL_URL", omni_url)
        self.OMNIPARSER_GPU_URL = os.getenv("OMNIPARSER_GPU_URL", "")
        self.OMNIPARSER_TIMEOUT = int(
            os.getenv("OMNIPARSER_TIMEOUT", default_timeout)
        )
        self.OMNIPARSER_RETRY = int(
            os.getenv(
                "OMNIPARSER_RETRY",
                "0" if ":9800" in omni_url else "1",
            )
        )
        self.OMNIPARSER_RETRY_DELAY = float(
            os.getenv("OMNIPARSER_RETRY_DELAY", "3.0")
        )
        self.OMNIPARSER_PROBE_TIMEOUT = float(
            os.getenv("OMNIPARSER_PROBE_TIMEOUT", "3.0")
        )
        self.OMNIPARSER_LOCAL_TIMEOUT = float(
            os.getenv("OMNIPARSER_LOCAL_TIMEOUT", default_timeout)
        )
        self.OMNIPARSER_LOCAL_MAX_SIDE = int(
            os.getenv("OMNIPARSER_LOCAL_MAX_SIDE", "960")
        )
        self.OMNIPARSER_MAX_ELEMENTS = int(
            os.getenv("OMNIPARSER_MAX_ELEMENTS", "80")
        )
        self.OMNIPARSER_MIN_AREA = int(os.getenv("OMNIPARSER_MIN_AREA", "100"))
        self.OMNIPARSER_MODEL = os.getenv("OMNIPARSER_MODEL", "")
        self.OMNIPARSER_IMGSZ = int(os.getenv("OMNIPARSER_IMGSZ", "1280"))
        self.OMNIPARSER_BOX_THRESHOLD = float(
            os.getenv("OMNIPARSER_BOX_THRESHOLD", "0.05")
        )
        self.OMNIPARSER_IOU_THRESHOLD = float(
            os.getenv("OMNIPARSER_IOU_THRESHOLD", "0.1")
        )

        self.DETECTOR_BACKEND = os.getenv("DETECTOR_BACKEND", "auto")
        self.DETECTOR_AUTO_FALLBACK_REPLICATE = (
            os.getenv("DETECTOR_AUTO_FALLBACK_REPLICATE", "false").lower() == "true"
        )
        self.ALLOW_DETECTOR_FALLBACK = (
            os.getenv("ALLOW_DETECTOR_FALLBACK", "false").lower() == "true"
        )
        self.REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

        self.USE_REAL_LLM = os.getenv("USE_REAL_LLM", "true").lower() == "true"
        self.STRICT_FINGERPRINT = (
            os.getenv("STRICT_FINGERPRINT", "false").lower() == "true"
        )
        self.INTENT_MODEL_PATH = os.getenv(
            "INTENT_MODEL_PATH", "server/services/intent/model"
        )

        # Routing: auto | fast (L4 vision) | balanced (L3 deferred) | precision (L3 OmniParser)
        self.ROUTING_MODE = os.getenv("ROUTING_MODE", "auto").lower()
        self.BROWSER_PLUGIN_ENABLED = (
            os.getenv("BROWSER_PLUGIN_ENABLED", "true").lower() == "true"
        )
        self.PER_STEP_LOCATE = (
            os.getenv("PER_STEP_LOCATE", "true").lower() == "true"
        )
        self.SCREENSHOT_MAX_SIDE = int(os.getenv("SCREENSHOT_MAX_SIDE", "720"))
        self.INSPECT_MAX_SIDE = int(os.getenv("INSPECT_MAX_SIDE", "960"))

        # L4 Vision 快路径（独立于 L3 / OmniParser）
        self.L4_PLANNER_MODEL = os.getenv("L4_PLANNER_MODEL", "")
        self.L4_LOCATOR_MODEL = os.getenv("L4_LOCATOR_MODEL", "")
        self.L4_PLANNER_USE_VISION = os.getenv("L4_PLANNER_USE_VISION", "false")
        self.L4_PIPELINE_ENABLED = os.getenv("L4_PIPELINE_ENABLED", "true")
        self.L4_STRICT_LOCATE = os.getenv("L4_STRICT_LOCATE", "true")
        self.L4_SCREEN_HINTS = os.getenv("L4_SCREEN_HINTS", "true")
        self.L4_PLANNER_MAX_TOKENS = int(os.getenv("L4_PLANNER_MAX_TOKENS", "900"))
        self.L4_LOCATOR_MAX_TOKENS = int(os.getenv("L4_LOCATOR_MAX_TOKENS", "400"))
        self.L4_PLANNER_TIMEOUT = float(os.getenv("L4_PLANNER_TIMEOUT", "15"))
        self.L4_LOCATOR_TIMEOUT = os.getenv("L4_LOCATOR_TIMEOUT", "")
        self.L4_UPLOAD_MAX_SIDE = int(os.getenv("L4_UPLOAD_MAX_SIDE", "1280"))


settings = Config()


def reload_settings() -> None:
    """重新读取 server/.env 并刷新 settings 实例。"""
    settings.reload()
