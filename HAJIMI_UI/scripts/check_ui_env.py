#!/usr/bin/env python3
# [VERIFY] 验收脚本 — B 端 UI 依赖自检（PyQt5 / QtSvg）
# 运行: python scripts/check_ui_env.py  （setup.bat 会自动调用）
"""Verify B-end UI runtime dependencies before main.py (L5 auto-execute only)."""
from __future__ import annotations

import sys

CHECKS = [
    ("PyQt5", "PyQt5"),
    ("PyQt5.QtSvg", "PyQt5 (QtSvg module)"),
]


def main() -> int:
    print(f"Python {sys.version.split()[0]} ({sys.executable})")
    missing: list[str] = []
    for module, pip_name in CHECKS:
        try:
            __import__(module)
            print(f"  OK  {pip_name}")
        except ImportError:
            print(f"  FAIL {pip_name}")
            missing.append(pip_name)

    if missing:
        print("\nInstall missing packages:")
        print("  pip install -r requirements.txt")
        if any("QtSvg" in m for m in missing):
            print("  pip install --force-reinstall PyQt5")
        return 1

    print("\nUI environment OK. Start backend with 启动全栈.bat, then: python main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
