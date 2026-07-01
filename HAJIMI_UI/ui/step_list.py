from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal


class StepCard(QWidget):
    """HTML .step-card"""

    def __init__(self, index, description, parent=None):
        super().__init__(parent)
        self.index = index
        self.status = "pending"
        self.setObjectName("StepCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.num_label = QLabel(str(index + 1))
        self.num_label.setObjectName("StepCardNum")
        self.num_label.setFixedSize(20, 20)
        self.num_label.setAlignment(Qt.AlignCenter)

        self.desc_label = QLabel(description)
        self.desc_label.setObjectName("StepCardContent")
        self.desc_label.setWordWrap(True)
        self.desc_label.setMinimumWidth(0)
        self.desc_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addWidget(self.num_label, 0, Qt.AlignTop)
        layout.addWidget(self.desc_label, 1)

        self.set_status("pending")

    def set_status(self, status):
        self.status = status
        prop = {"active": "active", "done": "completed", "pending": "pending"}.get(
            status, status
        )
        self.setProperty("stepStatus", prop)
        self.num_label.setProperty("stepStatus", prop)
        self.desc_label.setProperty("stepStatus", prop)
        for w in (self, self.num_label, self.desc_label):
            w.style().unpolish(w)
            w.style().polish(w)


class StepListWidget(QWidget):
    """HTML .blueprint-container / step list container."""

    step_status_changed = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StepCardList")
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(8)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.items = []

    def add_step(self, description):
        idx = len(self.items)
        item = StepCard(idx, description)
        self._layout.addWidget(item)
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
        if active_index >= len(descriptions):
            for i in range(len(descriptions)):
                self.set_step_status(i, "done")
            return
        for i, _ in enumerate(descriptions):
            if i < active_index:
                self.set_step_status(i, "done")
            elif i == active_index:
                self.set_step_status(i, "active")
            else:
                self.set_step_status(i, "pending")


# Backward compatibility alias
StepItem = StepCard
