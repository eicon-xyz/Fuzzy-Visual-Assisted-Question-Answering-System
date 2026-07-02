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

    # OmniParser GPU API (校园网 GPU 服务器 :9800)
    # 详见 项目文档/GPU-API接入指南-配置修改.md
    OMNIPARSER_URL: str = os.getenv(
        "OMNIPARSER_URL", "http://127.0.0.1:9800"
    )
    OMNIPARSER_TIMEOUT: int = int(os.getenv("OMNIPARSER_TIMEOUT", "30"))
    OMNIPARSER_RETRY: int = int(os.getenv("OMNIPARSER_RETRY", "1"))
    OMNIPARSER_RETRY_DELAY: float = float(os.getenv("OMNIPARSER_RETRY_DELAY", "3.0"))

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
