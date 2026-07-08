#!/usr/bin/env python
"""Quick test: launch NetEase Cloud Music via Win+Search"""
import sys; sys.path.insert(0, '.')
from server.services.launcher import launch_app
result = launch_app('网易云音乐')
print(result)
