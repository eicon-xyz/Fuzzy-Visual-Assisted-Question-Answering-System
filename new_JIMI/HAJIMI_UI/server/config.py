"""
HAJIMI Server 配置文件 — OmniParser + 视觉 LLM 混合版本

远程 GPU OmniParser 做元素检测，多模态 LLM 做规划与验证。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from core.defaults import DEFAULT_A_PORT, DEFAULT_DEMO_KEY

# 加载 .env 文件 — 先检查 server/.env，再检查项目根目录
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()  # fallback: 从当前工作目录查找


class Config:
    """HAJIMI 服务配置"""

    # 服务
    HOST: str = os.getenv("HAJIMI_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("HAJIMI_PORT", str(DEFAULT_A_PORT)))
    DEBUG: bool = os.getenv("HAJIMI_DEBUG", "true").lower() == "true"

    # Demo 认证
    DEMO_KEY: str = os.getenv("HAJIMI_DEMO_KEY", DEFAULT_DEMO_KEY)

    # ═════════════════════════════════════════════════════════════════════
    # OmniParser 远程 GPU
    # ═════════════════════════════════════════════════════════════════════
    OMNIPARSER_URL: str = os.getenv("OMNIPARSER_URL", "http://127.0.0.1:9800")
    OMNIPARSER_TIMEOUT: int = int(os.getenv("OMNIPARSER_TIMEOUT", "30"))
    OMNIPARSER_RETRY: int = int(os.getenv("OMNIPARSER_RETRY", "1"))
    OMNIPARSER_RETRY_DELAY: float = float(os.getenv("OMNIPARSER_RETRY_DELAY", "3.0"))

    # ═════════════════════════════════════════════════════════════════════
    # LLM 提供商选择
    # ═════════════════════════════════════════════════════════════════════
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "qwen")

    # 通用 LLM（默认/回退）
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv(
        "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-vl-max")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "120"))

    # 各供应商独立配置
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.2-11b-vision-preview")

    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "")

    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2-vision")

    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
    QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "https://api.siliconflow.cn/v1")
    QWEN_MODEL: str = os.getenv("QWEN_MODEL", "qwen-vl-max")

    GLM_API_KEY: str = os.getenv("GLM_API_KEY", "")
    GLM_BASE_URL: str = os.getenv("GLM_BASE_URL", "")
    GLM_MODEL: str = os.getenv("GLM_MODEL", "")

    # DeepSeek 兼容
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_TIMEOUT: int = int(os.getenv("DEEPSEEK_TIMEOUT", "30"))

    # ═════════════════════════════════════════════════════════════════════
    # Memory extractor — cheap model for background memory extraction
    # ═════════════════════════════════════════════════════════════════════
    MEMORY_EXTRACTOR_MODEL: str = os.getenv("MEMORY_EXTRACTOR_MODEL", "qwen-turbo")
    MEMORY_EXTRACTOR_PROVIDER: str = os.getenv("MEMORY_EXTRACTOR_PROVIDER", "qwen")

    # ═════════════════════════════════════════════════════════════════════
    # 特性开关
    # ═════════════════════════════════════════════════════════════════════
    USE_REAL_LLM: bool = os.getenv("USE_REAL_LLM", "true").lower() == "true"
    STRICT_FINGERPRINT: bool = (
        os.getenv("STRICT_FINGERPRINT", "false").lower() == "true"
    )

    # SetFit 意图分类模型
    INTENT_MODEL_PATH: str = os.getenv(
        "INTENT_MODEL_PATH", "server/services/intent/model"
    )

    # Agent loop tuning
    MAX_TOOL_CALL_ROUNDS: int = int(os.getenv("MAX_TOOL_CALL_ROUNDS", "15"))
    STEP_RETRY_LIMIT: int = int(os.getenv("STEP_RETRY_LIMIT", "1"))


settings = Config()
