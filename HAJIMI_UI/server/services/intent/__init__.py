"""
意图理解服务
负责将用户查询分类到九大意图域
"""
from server.services.intent.setfit_classifier import classify_intent, reset_classifier

__all__ = ["classify_intent", "reset_classifier"]
