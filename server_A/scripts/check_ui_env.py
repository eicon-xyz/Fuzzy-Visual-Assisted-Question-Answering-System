#!/usr/bin/env python3
"""Verify B-end UI runtime dependencies before main.py."""
from __future__ import annotations

import sys

CHECKS = [
    ("PyQt5", "PyQt5"),
    ("PyQt5.QtSvg", "PyQt5 (QtSvg module)"),
    ("cv2", "opencv-python"),
    ("PIL", "Pillow"),
    ("mss", "mss"),
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
        print(f"  pip install -r requirements.txt")
        if any("QtSvg" in m for m in missing):
            print("  pip install --force-reinstall PyQt5")
        return 1

    print("\nUI environment OK. Run: set HAJIMI_MOCK_ONLY=1 && python main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
