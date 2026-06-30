"""
HAJIMI Server Demo 配置文件
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()


class Config:
    """Demo 阶段配置"""

    # 服务
    HOST: str = os.getenv("HAJIMI_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("HAJIMI_PORT", "8000"))
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

    # Local OmniParser V2 API (deployed at D:\ominprester)
    OMNIPARSER_URL: str = os.getenv(
        "OMNIPARSER_URL", "http://127.0.0.1:9800"
    )
    OMNIPARSER_TIMEOUT: int = int(os.getenv("OMNIPARSER_TIMEOUT", "30"))

    # Demo 简化开关
    USE_REAL_LLM: bool = os.getenv("USE_REAL_LLM", "true").lower() == "true"
    STRICT_FINGERPRINT: bool = (
        os.getenv("STRICT_FINGERPRINT", "false").lower() == "true"
    )


settings = Config()
