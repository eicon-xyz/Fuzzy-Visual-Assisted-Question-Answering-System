"""
HAJIMI Server Demo 配置文件
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 从 server/.env 加载（无论从项目根还是 server/ 目录启动）
load_dotenv(Path(__file__).resolve().parent / ".env")


class Config:
    """Demo 阶段配置"""

    # 服务
    HOST: str = os.getenv("HAJIMI_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("HAJIMI_PORT", "8010"))
    DEBUG: bool = os.getenv("HAJIMI_DEBUG", "true").lower() == "true"

    # Demo 认证
    DEMO_KEY: str = os.getenv("HAJIMI_DEMO_KEY", "hajimi-demo-2026")

    # DeepSeek API
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_TIMEOUT: int = int(os.getenv("DEEPSEEK_TIMEOUT", "30"))

    # Demo 简化开关
    USE_REAL_LLM: bool = os.getenv("USE_REAL_LLM", "true").lower() == "true"
    STRICT_FINGERPRINT: bool = (
        os.getenv("STRICT_FINGERPRINT", "false").lower() == "true"
    )

    # UI 检测器（Replicate OmniParser）
    DETECTOR_BACKEND: str = os.getenv("DETECTOR_BACKEND", "replicate_omniparser")
    REPLICATE_API_TOKEN: str = os.getenv("REPLICATE_API_TOKEN", "")
    OMNIPARSER_MODEL: str = os.getenv(
        "OMNIPARSER_MODEL",
        "microsoft/omniparser-v2:"
        "49cf3d41b8d3aca1360514e83be4c97131ce8f0d99abfc365526d8384caa88df",
    )
    OMNIPARSER_BOX_THRESHOLD: float = float(os.getenv("OMNIPARSER_BOX_THRESHOLD", "0.05"))
    OMNIPARSER_IOU_THRESHOLD: float = float(os.getenv("OMNIPARSER_IOU_THRESHOLD", "0.1"))
    OMNIPARSER_IMGSZ: int = int(os.getenv("OMNIPARSER_IMGSZ", "640"))
    OMNIPARSER_MAX_ELEMENTS: int = int(os.getenv("OMNIPARSER_MAX_ELEMENTS", "80"))
    OMNIPARSER_MIN_AREA: int = int(os.getenv("OMNIPARSER_MIN_AREA", "100"))
    OMNIPARSER_TIMEOUT: int = int(os.getenv("OMNIPARSER_TIMEOUT", "60"))
    OMNIPARSER_LOCAL_URL: str = os.getenv(
        "OMNIPARSER_LOCAL_URL", "http://127.0.0.1:8000"
    )
    OMNIPARSER_LOCAL_TIMEOUT: int = int(
        os.getenv("OMNIPARSER_LOCAL_TIMEOUT", "360")
    )
    OMNIPARSER_LOCAL_MAX_SIDE: int = int(
        os.getenv("OMNIPARSER_LOCAL_MAX_SIDE", "960")
    )
    ALLOW_DETECTOR_FALLBACK: bool = (
        os.getenv("ALLOW_DETECTOR_FALLBACK", "false").lower() == "true"
    )
    REQUIRE_IMAGE: bool = os.getenv("REQUIRE_IMAGE", "true").lower() == "true"


settings = Config()
