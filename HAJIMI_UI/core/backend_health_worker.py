"""Background worker for periodic backend health / connection status."""
from PyQt5.QtCore import QThread, pyqtSignal

from core.api_client import get_api_status_with_connection


class BackendHealthWorker(QThread):
    sig_ready = pyqtSignal(str, str, bool)

    def run(self):
        try:
            text, msg_type, connected = get_api_status_with_connection()
            self.sig_ready.emit(text, msg_type, connected)
        except Exception as exc:
            self.sig_ready.emit(
                f"后端状态检测失败: {exc}",
                "system danger",
                False,
            )
