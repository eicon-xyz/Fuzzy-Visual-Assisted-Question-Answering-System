"""
HAJIMI Server Demo 配置文件
"""
import os
from dotenv import load_dotenv

from core.defaults import (
    DEFAULT_A_PORT,
    DEFAULT_DEMO_KEY,
    DEFAULT_OMNI_LOCAL_URL,
)

# 加载 .env 文件（如果存在）
load_dotenv()

_OMNI_URL = os.getenv("OMNIPARSER_URL", DEFAULT_OMNI_LOCAL_URL)


class Config:
    """Demo 阶段配置"""

    # 服务
    HOST: str = os.getenv("HAJIMI_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("HAJIMI_PORT", str(DEFAULT_A_PORT)))
    DEBUG: bool = os.getenv("HAJIMI_DEBUG", "true").lower() == "true"

    # Demo 认证
    DEMO_KEY: str = os.getenv("HAJIMI_DEMO_KEY", DEFAULT_DEMO_KEY)

    # LLM API (支持多模态的模型)
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv(
        "LLM_BASE_URL", "https://api.siliconflow.cn/v1"
    )
    LLM_MODEL: str = os.getenv("LLM_MODEL", "Qwen/Qwen3.6-35B-A3B")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))

    # DeepSeek API (保留兼容)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_TIMEOUT: int = int(os.getenv("DEEPSEEK_TIMEOUT", "30"))

    # OmniParser — 本地默认 :8002；校园 GPU 在 .env 覆盖为 :9800
    OMNIPARSER_URL: str = _OMNI_URL
    OMNIPARSER_LOCAL_URL: str = os.getenv("OMNIPARSER_LOCAL_URL", _OMNI_URL)
    OMNIPARSER_GPU_URL: str = os.getenv("OMNIPARSER_GPU_URL", "")
    OMNIPARSER_TIMEOUT: int = int(os.getenv("OMNIPARSER_TIMEOUT", "360"))
    OMNIPARSER_RETRY: int = int(os.getenv("OMNIPARSER_RETRY", "1"))
    OMNIPARSER_RETRY_DELAY: float = float(os.getenv("OMNIPARSER_RETRY_DELAY", "3.0"))
    OMNIPARSER_PROBE_TIMEOUT: float = float(os.getenv("OMNIPARSER_PROBE_TIMEOUT", "3.0"))
    OMNIPARSER_LOCAL_TIMEOUT: float = float(os.getenv("OMNIPARSER_LOCAL_TIMEOUT", "360"))
    OMNIPARSER_LOCAL_MAX_SIDE: int = int(os.getenv("OMNIPARSER_LOCAL_MAX_SIDE", "1920"))
    OMNIPARSER_MAX_ELEMENTS: int = int(os.getenv("OMNIPARSER_MAX_ELEMENTS", "80"))
    OMNIPARSER_MIN_AREA: int = int(os.getenv("OMNIPARSER_MIN_AREA", "100"))
    OMNIPARSER_MODEL: str = os.getenv("OMNIPARSER_MODEL", "")
    OMNIPARSER_IMGSZ: int = int(os.getenv("OMNIPARSER_IMGSZ", "1280"))
    OMNIPARSER_BOX_THRESHOLD: float = float(os.getenv("OMNIPARSER_BOX_THRESHOLD", "0.05"))
    OMNIPARSER_IOU_THRESHOLD: float = float(os.getenv("OMNIPARSER_IOU_THRESHOLD", "0.1"))

    # ui_detector legacy (deprecated; routes use omniparser_client)
    DETECTOR_BACKEND: str = os.getenv("DETECTOR_BACKEND", "auto")
    DETECTOR_AUTO_FALLBACK_REPLICATE: bool = (
        os.getenv("DETECTOR_AUTO_FALLBACK_REPLICATE", "false").lower() == "true"
    )
    ALLOW_DETECTOR_FALLBACK: bool = (
        os.getenv("ALLOW_DETECTOR_FALLBACK", "false").lower() == "true"
    )
    REPLICATE_API_TOKEN: str = os.getenv("REPLICATE_API_TOKEN", "")

    # Demo 简化开关
    USE_REAL_LLM: bool = os.getenv("USE_REAL_LLM", "true").lower() == "true"
    STRICT_FINGERPRINT: bool = (
        os.getenv("STRICT_FINGERPRINT", "false").lower() == "true"
    )

    # SetFit 模型路径
    INTENT_MODEL_PATH: str = os.getenv(
        "INTENT_MODEL_PATH", "server/services/intent/model"
    )


settings = Config()
