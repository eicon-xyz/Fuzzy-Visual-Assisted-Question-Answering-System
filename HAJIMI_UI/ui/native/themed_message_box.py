"""Theme-aware QMessageBox styling — local QSS only, no global theme changes."""
from __future__ import annotations

from typing import Optional

from PyQt5.QtWidgets import QCheckBox, QMessageBox, QWidget

from core.user_settings import load_user_settings


def _messagebox_stylesheet(theme_id: str) -> str:
    if theme_id == "variant_orange_cat":
        return """
            QMessageBox {
                background-color: #FFF2E2;
            }
            QMessageBox QLabel {
                color: #3A271B;
                font-size: 13px;
            }
            QMessageBox QCheckBox {
                color: #3A271B;
            }
            QMessageBox QPushButton {
                min-width: 72px;
                padding: 6px 14px;
                color: #3A271B;
                background-color: rgba(255, 179, 102, 0.25);
                border: 1px solid rgba(232, 149, 64, 0.45);
                border-radius: 6px;
            }
            QMessageBox QPushButton:hover {
                background-color: rgba(255, 179, 102, 0.4);
            }
        """
    if theme_id == "variant_luxury":
        return """
            QMessageBox {
                background-color: #141210;
            }
            QMessageBox QLabel {
                color: #EBE4D8;
                font-size: 13px;
            }
            QMessageBox QCheckBox {
                color: #EBE4D8;
            }
            QMessageBox QPushButton {
                min-width: 72px;
                padding: 6px 14px;
                color: #EBE4D8;
                background-color: rgba(201, 168, 76, 0.15);
                border: 1px solid rgba(201, 168, 76, 0.35);
                border-radius: 6px;
            }
            QMessageBox QPushButton:hover {
                background-color: rgba(201, 168, 76, 0.28);
            }
        """
    return """
        QMessageBox {
            background-color: #0f172a;
        }
        QMessageBox QLabel {
            color: #f1f5f9;
            font-size: 13px;
        }
        QMessageBox QCheckBox {
            color: #f1f5f9;
        }
        QMessageBox QPushButton {
            min-width: 72px;
            padding: 6px 14px;
            color: #f1f5f9;
            background-color: rgba(51, 65, 85, 0.9);
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 6px;
        }
        QMessageBox QPushButton:hover {
            background-color: rgba(71, 85, 105, 0.95);
        }
    """


def themed_warning_consent(
    parent: Optional[QWidget],
    title: str,
    text: str,
    *,
    checkbox_label: str = "不再提示",
    theme_id: str | None = None,
) -> tuple[bool, bool]:
    """Show warning QMessageBox with optional checkbox. Returns (accepted, checkbox_checked)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    dont_show = QCheckBox(checkbox_label)
    box.setCheckBox(dont_show)
    box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    tid = theme_id or load_user_settings().get("ui_theme", "current")
    box.setStyleSheet(_messagebox_stylesheet(str(tid)))
    accepted = box.exec_() == QMessageBox.Ok
    return accepted, dont_show.isChecked()
