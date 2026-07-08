from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

class StepItem(QWidget):
    """单个步骤项，显示编号、描述，并支持三种状态"""
    def __init__(self, index, description, parent=None):
        super().__init__(parent)
        self.index = index
        self.status = 'pending'
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self.num_label = QLabel(str(index+1))
        self.num_label.setFixedSize(20, 20)
        self.num_label.setAlignment(Qt.AlignCenter)
        self.num_label.setStyleSheet("""
            background-color: #64748b;
            color: white;
            border-radius: 10px;
            font-weight: bold;
            font-size: 11px;
        """)

        self.desc_label = QLabel(description)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #94a3b8; font-size: 13px;")

        layout.addWidget(self.num_label)
        layout.addWidget(self.desc_label, 1)

        self.set_status('pending')

    def set_status(self, status):
        self.status = status
        if status == 'active':
            self.setStyleSheet("""
                QWidget {
                    background-color: rgba(90,158,196,0.12);
                    border: 1px solid #5a9ec4;
                    border-radius: 8px;
                    margin: 3px 0px;
                }
            """)
            self.num_label.setStyleSheet("""
                background-color: #5a9ec4;
                color: white;
                border-radius: 10px;
                font-weight: bold;
                font-size: 11px;
            """)
            self.desc_label.setStyleSheet("color: #f1f5f9; font-weight: 500; font-size: 13px;")
        elif status == 'done':
            self.setStyleSheet("""
                QWidget {
                    background-color: rgba(255,255,255,0.02);
                    border: 1px solid rgba(255,255,255,0.06);
                    border-radius: 8px;
                    margin: 3px 0px;
                    opacity: 0.4;
                }
            """)
            self.num_label.setStyleSheet("""
                background-color: #2ecc71;
                color: white;
                border-radius: 10px;
                font-weight: bold;
                font-size: 11px;
            """)
            self.desc_label.setStyleSheet("color: #94a3b8; font-size: 13px;")
        else:  # pending
            self.setStyleSheet("""
                QWidget {
                    background-color: rgba(255,255,255,0.04);
                    border: 1px solid rgba(255,255,255,0.06);
                    border-radius: 8px;
                    margin: 3px 0px;
                }
            """)
            self.num_label.setStyleSheet("""
                background-color: #64748b;
                color: white;
                border-radius: 10px;
                font-weight: bold;
                font-size: 11px;
            """)
            self.desc_label.setStyleSheet("color: #94a3b8; font-size: 13px;")


class StepListWidget(QWidget):
    """步骤列表容器，管理多个 StepItem"""
    step_status_changed = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(6)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.items = []

    def add_step(self, description):
        idx = len(self.items)
        item = StepItem(idx, description)
        self.layout.addWidget(item)
        self.items.append(item)
        return idx

    def clear(self):
        for item in self.items:
            item.deleteLater()
        self.items.clear()

    def set_step_status(self, index, status):
        if 0 <= index < len(self.items):
            self.items[index].set_status(status)
            self.step_status_changed.emit(index, status)

    def set_steps(self, descriptions, active_index=0):
        self.clear()
        for desc in descriptions:
            self.add_step(desc)
        for i, _ in enumerate(descriptions):
            if i < active_index:
                self.set_step_status(i, 'done')
            elif i == active_index:
                self.set_step_status(i, 'active')
            else:
                self.set_step_status(i, 'pending')