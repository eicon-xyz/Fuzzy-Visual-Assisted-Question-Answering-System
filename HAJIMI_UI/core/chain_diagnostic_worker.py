"""Background worker for chain diagnostics."""
from PyQt5.QtCore import QThread, pyqtSignal

from core.chain_diagnostics import format_report_human, run_full_diagnostic


class ChainDiagnosticWorker(QThread):
    sig_done = pyqtSignal(str)
    sig_error = pyqtSignal(str)

    def __init__(self, include_parse: bool = False, include_e2e: bool = False):
        super().__init__()
        self._include_parse = include_parse
        self._include_e2e = include_e2e

    def run(self):
        try:
            report = run_full_diagnostic(
                include_parse=self._include_parse,
                include_e2e_inspect=self._include_e2e,
            )
            self.sig_done.emit(format_report_human(report))
        except Exception as exc:
            self.sig_error.emit(str(exc))
