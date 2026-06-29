"""
HAJIMI Client — 集成端（角色 C）
==================================
包含语音交互（ASR/TTS）、审计代理、配置拉取、B-C 集成控制器等模块。

子包:
- voice/       : ASR 语音识别 + TTS 语音合成
- audit/       : 审计日志本地队列 + 批量 HTTP 上报
- config/      : 服务端配置定时轮询
- integration/ : B-C PyQt5 信号集成控制器
"""

__version__ = "1.0.0"
__author__ = "HAJIMI Team — Role C (Integration / Voice / Admin)"
