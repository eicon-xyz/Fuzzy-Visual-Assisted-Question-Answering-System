"""
LLM 服务层
负责与 DeepSeek 等大模型 API 交互
"""
from server.services.llm.client import call_deepseek


__all__ = ["call_deepseek"]
