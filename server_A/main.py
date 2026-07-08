# main.py
import os
import sys
import threading

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor

from core.deployment_resolver import get_startup_hints
from core.user_settings import apply_user_settings, load_user_settings

_settings = load_user_settings()
# 保存 start_all.bat / 外部预设的 HAJIMI_AUTO_LAUNCH_A_END，防止 apply_user_settings 覆盖
_EXT_AUTO_LAUNCH = os.environ.get("HAJIMI_AUTO_LAUNCH_A_END")
apply_user_settings(_settings)
# 恢复外部预设值
if _EXT_AUTO_LAUNCH is not None:
    os.environ["HAJIMI_AUTO_LAUNCH_A_END"] = _EXT_AUTO_LAUNCH
    import config
    config.reload_from_env()
STARTUP_HINTS = get_startup_hints(_settings)

from ui.main_widget import MainWidget


def _apply_dark_palette(app: QApplication):
    palette = QPalette()
    text = QColor("#f1f5f9")
    window = QColor("#0f172a")
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.Base, QColor("#1e293b"))
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.ToolTipBase, window)
    palette.setColor(QPalette.PlaceholderText, QColor("#64748b"))
    app.setPalette(palette)


def _auto_launch_a_end():
    """在后台自动启动 A 端（本地模式），不阻塞 UI 启动。"""
    import time
    from core.a_end_launcher import ensure_a_end_running

    # 等 A 端有足够时间完成初始化（uvicorn 加载模块 + init_db 等）
    time.sleep(8)
    ok, msg = ensure_a_end_running()
    if ok:
        print("[HAJIMI] A-end ready (already running or auto-started)")
    elif msg:
        print(f"[HAJIMI] auto-start A-end: {msg}")


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QApplication(sys.argv)
    _apply_dark_palette(app)
    widget = MainWidget(startup_hints=STARTUP_HINTS)
    widget.show()

    # 本地模式下后台自动启动 A 端（不等待用户输入）
    # start_all.bat 已启动 A 端时设 HAJIMI_AUTO_LAUNCH_A_END=0 可以跳过
    if _settings.get("deployment_mode", "local") != "intranet" and _EXT_AUTO_LAUNCH is None and _settings.get("auto_launch_a_end", True):
        threading.Thread(target=_auto_launch_a_end, daemon=True).start()

    sys.exit(app.exec_())