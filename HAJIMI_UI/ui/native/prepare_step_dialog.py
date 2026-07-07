from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QWidget,
    QScrollArea,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal

from core.prepare_guidance import PrepareScene, PreparePreset
from ui.native.widgets import DialogCard, center_dialog_on_widget

_DIALOG_MIN_WIDTH = 360
_OPTIONS_MAX_HEIGHT = 240


class _PresetOptionRow(QWidget):
    """侧栏中的单个预设选项。"""

    chosen = pyqtSignal(str)

    def __init__(self, preset: PreparePreset, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(4)

        btn = QPushButton(preset.label)
        btn.setObjectName("StepBtn")
        btn.clicked.connect(lambda: self.chosen.emit(preset.id))
        layout.addWidget(btn)

        if preset.description:
            desc = QLabel(preset.description)
            desc.setObjectName("DialogSub")
            desc.setWordWrap(True)
            layout.addWidget(desc)


class PrepareStepDialog(QDialog):
    """定位失败或需手动完成时，展示情境文案与多预设引导。"""

    preset_chosen = pyqtSignal(str)
    dismissed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setMinimumWidth(_DIALOG_MIN_WIDTH)
        self._step_desc = ""
        self._scene: PrepareScene | None = None
        self._options_expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = DialogCard("prepare")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self._title_label = QLabel("请先完成这一步")
        self._title_label.setObjectName("DialogTitlePrepare")
        layout.addWidget(self._title_label)

        self._body_label = QLabel("")
        self._body_label.setObjectName("DialogBody")
        self._body_label.setWordWrap(True)
        layout.addWidget(self._body_label)

        primary_row = QHBoxLayout()
        self._dismiss_btn = QPushButton("稍后")
        self._dismiss_btn.setObjectName("StepBtn")
        self._dismiss_btn.clicked.connect(self._on_later)

        self._primary_btn = QPushButton("重新定位")
        self._primary_btn.setObjectName("StepBtnPrimary")
        self._primary_btn.clicked.connect(self._on_primary)

        primary_row.addWidget(self._dismiss_btn)
        primary_row.addWidget(self._primary_btn)
        layout.addLayout(primary_row)

        self._more_btn = QPushButton("点我查看更多选项 ▾")
        self._more_btn.setObjectName("DialogLinkBtn")
        self._more_btn.setFlat(True)
        self._more_btn.setCursor(Qt.PointingHandCursor)
        self._more_btn.setMinimumHeight(32)
        self._more_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._more_btn.clicked.connect(self._toggle_options)
        layout.addWidget(self._more_btn)

        self._options_scroll = QScrollArea()
        self._options_scroll.setObjectName("PrepareOptionsDrawer")
        self._options_scroll.setWidgetResizable(True)
        self._options_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._options_scroll.setMaximumHeight(_OPTIONS_MAX_HEIGHT)
        self._options_scroll.hide()

        self._options_inner = QWidget()
        self._options_layout = QVBoxLayout(self._options_inner)
        self._options_layout.setContentsMargins(0, 8, 0, 0)
        self._options_layout.setSpacing(4)
        self._options_scroll.setWidget(self._options_inner)
        layout.addWidget(self._options_scroll)

        outer.addWidget(card)

    def show_guidance(self, scene: PrepareScene):
        self._set_options_expanded(False)
        self._clear_options_layout()

        self._scene = scene
        self._step_desc = scene.body
        self._title_label.setText(scene.title)
        self._body_label.setText(scene.body)

        primary = scene.primary_preset()
        if primary:
            self._primary_btn.setText(primary.label)
            self._primary_preset_id = primary.id
        else:
            self._primary_preset_id = "relocate"

        self._rebuild_options(scene)
        self._set_busy(False)
        self._reflow_and_center()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_hint(self, hint: str, step_desc: str = "", reason: str = "locate_failed"):
        """兼容旧接口。"""
        from core.prepare_guidance import resolve_prepare_scene

        step = {
            "description": step_desc or hint,
            "prepare_hint": hint,
            "locate_deferred": reason == "deferred",
        }
        scene = resolve_prepare_scene(
            step,
            force_deferred=reason == "deferred",
        )
        self.show_guidance(scene)

    def set_busy(self, busy: bool):
        self._set_busy(busy)

    def _clear_options_layout(self):
        while self._options_layout.count():
            item = self._options_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_options(self, scene: PrepareScene):
        self._clear_options_layout()
        for preset in scene.secondary_presets():
            row = _PresetOptionRow(preset)
            row.chosen.connect(self._on_option_chosen)
            self._options_layout.addWidget(row)
        self._more_btn.setVisible(bool(scene.secondary_presets()))

    def _set_options_expanded(self, expanded: bool):
        self._options_expanded = expanded
        self._options_scroll.setVisible(expanded)
        self._more_btn.setText(
            "收起选项 ▴" if expanded else "点我查看更多选项 ▾"
        )
        self._reflow_and_center()

    def _reflow_and_center(self):
        self._options_inner.adjustSize()
        self._options_scroll.updateGeometry()
        self.adjustSize()
        self.setMinimumWidth(_DIALOG_MIN_WIDTH)
        center_dialog_on_widget(self, self.parent())

    def _toggle_options(self):
        self._set_options_expanded(not self._options_expanded)

    def _set_busy(self, busy: bool):
        self._primary_btn.setEnabled(not busy)
        self._more_btn.setEnabled(not busy)
        for i in range(self._options_layout.count()):
            w = self._options_layout.itemAt(i).widget()
            if w:
                w.setEnabled(not busy)
        if busy:
            self._primary_btn.setText("处理中…")
        elif self._scene:
            primary = self._scene.primary_preset()
            if primary:
                self._primary_btn.setText(primary.label)

    def _emit_preset(self, preset_id: str):
        self._set_busy(True)
        self.preset_chosen.emit(preset_id)

    def _on_primary(self):
        self._emit_preset(getattr(self, "_primary_preset_id", "relocate"))

    def _on_option_chosen(self, preset_id: str):
        self._emit_preset(preset_id)

    def _on_later(self):
        self.hide()
        self._set_options_expanded(False)
        self.dismissed.emit(self._step_desc)
