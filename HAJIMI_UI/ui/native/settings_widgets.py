"""系统设置页可复用控件。"""
from __future__ import annotations

from PyQt5.QtCore import Qt, QObject, QEvent, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QFrame,
    QPushButton,
    QSlider,
)

from ui.native.luxury.qss import LUXURY_BG_MODES
from ui.native.luxury.title import DEFAULT_SCRIPT_FONT_ID, script_font_labels
from ui.native.shell_appearance import (
    DEFAULT_CRYSTAL_EDGE_SHADOW,
    DEFAULT_FONT_SIZE,
    DEFAULT_LUXURY_BG_MODE,
    DEFAULT_LUXURY_STAR_INTENSITY,
    DEFAULT_SHELL_ALPHA_COMPACT,
    DEFAULT_SHELL_ALPHA_MEDIUM,
    DEFAULT_SHELL_STYLE,
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    LUXURY_STAR_INTENSITY_MAX,
    LUXURY_THEME_ID,
    SHADOW_STRENGTH_MAX,
    SHELL_ALPHA_MAX,
    SHELL_ALPHA_MIN,
    SHELL_STYLES,
    default_crystal_shadow_strength,
    is_crystal_shell,
)
from ui.native.shell_paint import (
    DEFAULT_LIGHT_MODE,
    DEFAULT_QSS_BODY,
    DEFAULT_QSS_HIGHLIGHT,
    DEFAULT_QSS_HIGHLIGHT_PEAK,
    DEFAULT_TOP_LIGHT_PEAK,
    LIGHT_MODES,
    QSS_BODY_MODES,
    QSS_HIGHLIGHT_MODES,
)
from ui.native.theme_manager import THEME_LABELS
from ui.native.title_art import DEFAULT_TITLE_ART, TITLE_ART_MODES
from ui.native.widgets import CollapsibleSection


class SettingsEnterFilter(QObject):
    """Enter 提交（Shift+Enter 换行不适用单行框）。"""

    def __init__(self, submit_cb):
        super().__init__()
        self._submit = submit_cb

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._submit()
                return True
        return False


class SettingsFieldRow(QWidget):
    def __init__(
        self,
        label: str,
        placeholder: str = "",
        password: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("SettingsFieldRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)
        lbl = QLabel(label)
        lbl.setObjectName("SetRowLabel")
        lbl.setMinimumWidth(120)
        self.input = QLineEdit()
        self.input.setObjectName("SettingsInput")
        self.input.setPlaceholderText(placeholder)
        if password:
            self.input.setEchoMode(QLineEdit.Password)
        layout.addWidget(lbl, 0)
        layout.addWidget(self.input, 1)

    def text(self) -> str:
        return self.input.text().strip()

    def set_text(self, value: str) -> None:
        self.input.setText(value or "")

    def set_enabled(self, enabled: bool) -> None:
        self.input.setEnabled(enabled)


class DeploymentModeGroup(QFrame):
    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("部署模式")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel("本地启动：本机 OmniParser + A 端；内网 API：仅连接远程 A 端（需校园网/VPN）")
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._local = QRadioButton("本地启动")
        self._local.setObjectName("SettingsRadio")
        self._intranet = QRadioButton("内网 API")
        self._intranet.setObjectName("SettingsRadio")
        self._local.setChecked(True)

        self._group = QButtonGroup(self)
        self._group.addButton(self._local, 0)
        self._group.addButton(self._intranet, 1)
        self._group.buttonClicked.connect(self._on_click)

        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(self._local)
        row.addWidget(self._intranet)
        row.addStretch()
        layout.addLayout(row)

    def _on_click(self):
        self.mode_changed.emit(self.current_mode())

    def current_mode(self) -> str:
        return "intranet" if self._intranet.isChecked() else "local"

    def set_mode(self, mode: str) -> None:
        if mode == "intranet":
            self._intranet.setChecked(True)
        else:
            self._local.setChecked(True)


class UiAppearanceGroup(QFrame):
    """主题外观：Shell 风格 + 配色变体 + 透明度 / 字号 / Crystal 阴影。"""

    shell_style_changed = pyqtSignal(str)
    save_requested = pyqtSignal()
    appearance_preview_requested = pyqtSignal(dict)
    preview_layout_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("主题外观")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(
            "配色与轻奢选项切换后可即时预览；点「保存并应用」写入磁盘并在下次启动保留。"
        )
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._classic_shell_section = QWidget()
        classic_shell_l = QVBoxLayout(self._classic_shell_section)
        classic_shell_l.setContentsMargins(0, 0, 0, 0)
        classic_shell_l.setSpacing(4)
        classic_shell_l.addWidget(self._section_label("面板风格"))
        self._shell_style_buttons: dict[str, QRadioButton] = {}
        self._shell_style_group = QButtonGroup(self)
        shell_col = QVBoxLayout()
        shell_col.setSpacing(4)
        for idx, (style_id, label) in enumerate(SHELL_STYLES.items()):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._shell_style_group.addButton(rb, idx)
            self._shell_style_buttons[style_id] = rb
            shell_col.addWidget(rb)
        self._shell_style_group.buttonClicked.connect(self._on_shell_style_clicked)
        classic_shell_l.addLayout(shell_col)
        self._shell_style_buttons[DEFAULT_SHELL_STYLE].setChecked(True)
        layout.addWidget(self._classic_shell_section)

        layout.addWidget(self._section_label("配色方案"))
        self._theme_buttons: dict[str, QRadioButton] = {}
        self._theme_group = QButtonGroup(self)
        theme_col = QVBoxLayout()
        theme_col.setSpacing(4)
        for idx, (theme_id, label) in enumerate(THEME_LABELS.items()):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._theme_group.addButton(rb, idx)
            self._theme_buttons[theme_id] = rb
            theme_col.addWidget(rb)
        layout.addLayout(theme_col)
        self._theme_buttons["current"].setChecked(True)
        self._theme_group.buttonClicked.connect(self._on_theme_clicked)

        self._classic_alpha_section = QWidget()
        classic_alpha_l = QVBoxLayout(self._classic_alpha_section)
        classic_alpha_l.setContentsMargins(0, 0, 0, 0)
        classic_alpha_l.setSpacing(4)
        self._medium_alpha_label = QLabel()
        self._medium_alpha_label.setObjectName("HintTextSmall")
        self._medium_alpha_slider = QSlider(Qt.Horizontal)
        self._medium_alpha_slider.setRange(SHELL_ALPHA_MIN, SHELL_ALPHA_MAX)
        self._medium_alpha_slider.setValue(DEFAULT_SHELL_ALPHA_MEDIUM)
        self._medium_alpha_slider.valueChanged.connect(self._update_medium_alpha_label)
        row_m = QHBoxLayout()
        row_m.addWidget(QLabel("中窗透明度"))
        row_m.addWidget(self._medium_alpha_slider, 1)
        row_m.addWidget(self._medium_alpha_label)
        classic_alpha_l.addLayout(row_m)

        self._compact_alpha_label = QLabel()
        self._compact_alpha_label.setObjectName("HintTextSmall")
        self._compact_alpha_slider = QSlider(Qt.Horizontal)
        self._compact_alpha_slider.setRange(SHELL_ALPHA_MIN, SHELL_ALPHA_MAX)
        self._compact_alpha_slider.setValue(DEFAULT_SHELL_ALPHA_COMPACT)
        self._compact_alpha_slider.valueChanged.connect(self._update_compact_alpha_label)
        row_c = QHBoxLayout()
        row_c.addWidget(QLabel("小窗透明度"))
        row_c.addWidget(self._compact_alpha_slider, 1)
        row_c.addWidget(self._compact_alpha_label)
        classic_alpha_l.addLayout(row_c)
        layout.addWidget(self._classic_alpha_section)

        self._font_size_label = QLabel()
        self._font_size_label.setObjectName("HintTextSmall")
        self._font_size_slider = QSlider(Qt.Horizontal)
        self._font_size_slider.setRange(FONT_SIZE_MIN, FONT_SIZE_MAX)
        self._font_size_slider.setValue(DEFAULT_FONT_SIZE)
        self._font_size_slider.valueChanged.connect(self._update_font_size_label)
        row_f = QHBoxLayout()
        row_f.addWidget(QLabel("全局字号"))
        row_f.addWidget(self._font_size_slider, 1)
        row_f.addWidget(self._font_size_label)
        layout.addLayout(row_f)

        self._classic_shadow_section = QWidget()
        classic_shadow_l = QVBoxLayout(self._classic_shadow_section)
        classic_shadow_l.setContentsMargins(0, 0, 0, 0)
        classic_shadow_l.setSpacing(4)
        self._shadow_label = QLabel()
        self._shadow_label.setObjectName("HintTextSmall")
        self._shadow_slider = QSlider(Qt.Horizontal)
        self._shadow_slider.setRange(0, SHADOW_STRENGTH_MAX)
        self._shadow_slider.setValue(DEFAULT_CRYSTAL_EDGE_SHADOW)
        self._shadow_slider.valueChanged.connect(self._update_shadow_label)
        row_s = QHBoxLayout()
        row_s.addWidget(QLabel("Crystal 阴影"))
        row_s.addWidget(self._shadow_slider, 1)
        row_s.addWidget(self._shadow_label)
        classic_shadow_l.addLayout(row_s)

        shadow_hint = QLabel(
            "纯细边建议 0，极轻阴影建议 14；仅 Crystal 面板风格生效。"
        )
        shadow_hint.setObjectName("HintTextSmall")
        shadow_hint.setWordWrap(True)
        classic_shadow_l.addWidget(shadow_hint)
        layout.addWidget(self._classic_shadow_section)

        self._classic_title_section = QWidget()
        classic_title_l = QVBoxLayout(self._classic_title_section)
        classic_title_l.setContentsMargins(0, 0, 0, 0)
        classic_title_l.setSpacing(4)
        classic_title_l.addWidget(self._section_label("顶栏艺术字"))
        self._title_art_buttons: dict[str, QRadioButton] = {}
        self._title_art_group = QButtonGroup(self)
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        for idx, (mode_id, label) in enumerate(TITLE_ART_MODES.items()):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._title_art_group.addButton(rb, idx)
            self._title_art_buttons[mode_id] = rb
            title_col.addWidget(rb)
        classic_title_l.addLayout(title_col)
        self._title_art_buttons[DEFAULT_TITLE_ART].setChecked(True)
        layout.addWidget(self._classic_title_section)

        self._luxury_section = QWidget()
        luxury_l = QVBoxLayout(self._luxury_section)
        luxury_l.setContentsMargins(0, 0, 0, 0)
        luxury_l.setSpacing(6)
        luxury_l.addWidget(self._section_label("背景质感"))
        self._luxury_bg_buttons: dict[str, QRadioButton] = {}
        self._luxury_bg_group = QButtonGroup(self)
        bg_col = QVBoxLayout()
        bg_col.setSpacing(4)
        for idx, (mode_id, label) in enumerate(LUXURY_BG_MODES.items()):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._luxury_bg_group.addButton(rb, idx)
            self._luxury_bg_buttons[mode_id] = rb
            bg_col.addWidget(rb)
        self._luxury_bg_group.buttonClicked.connect(self._on_luxury_bg_clicked)
        luxury_l.addLayout(bg_col)
        self._luxury_bg_buttons[DEFAULT_LUXURY_BG_MODE].setChecked(True)

        self._luxury_star_section = CollapsibleSection("星空强度", expanded=False)
        self._luxury_star_label = QLabel()
        self._luxury_star_label.setObjectName("HintTextSmall")
        self._luxury_star_slider = QSlider(Qt.Horizontal)
        self._luxury_star_slider.setRange(0, LUXURY_STAR_INTENSITY_MAX)
        self._luxury_star_slider.setValue(DEFAULT_LUXURY_STAR_INTENSITY)
        self._luxury_star_slider.valueChanged.connect(self._update_luxury_star_label)
        self._luxury_star_slider.valueChanged.connect(self._emit_preview)
        star_row = QHBoxLayout()
        star_row.addWidget(QLabel("强度"))
        star_row.addWidget(self._luxury_star_slider, 1)
        star_row.addWidget(self._luxury_star_label)
        self._luxury_star_section.body_layout().addLayout(star_row)
        self._luxury_star_hint = QLabel("牛皮纸底不适用星空。")
        self._luxury_star_hint.setObjectName("HintTextSmall")
        self._luxury_star_hint.setWordWrap(True)
        self._luxury_star_hint.hide()
        self._luxury_star_section.body_layout().addWidget(self._luxury_star_hint)
        luxury_l.addWidget(self._luxury_star_section)

        self._luxury_font_section = CollapsibleSection("鎏金签名试选", expanded=False)
        self._luxury_font_buttons: dict[str, QRadioButton] = {}
        self._luxury_font_group = QButtonGroup(self)
        font_col = QVBoxLayout()
        font_col.setSpacing(4)
        for idx, (font_id, label) in enumerate(script_font_labels().items()):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._luxury_font_group.addButton(rb, idx)
            self._luxury_font_buttons[font_id] = rb
            font_col.addWidget(rb)
        self._luxury_font_section.body_layout().addLayout(font_col)
        self._luxury_font_buttons[DEFAULT_SCRIPT_FONT_ID].setChecked(True)
        self._luxury_font_group.buttonClicked.connect(self._emit_preview)
        luxury_l.addWidget(self._luxury_font_section)
        self._luxury_star_section.toggled.connect(self._emit_preview_layout)
        self._luxury_font_section.toggled.connect(self._emit_preview_layout)
        layout.addWidget(self._luxury_section)

        self._crystal_light_section = QWidget()
        crystal_l = QVBoxLayout(self._crystal_light_section)
        crystal_l.setContentsMargins(0, 0, 0, 0)
        crystal_l.setSpacing(6)
        crystal_l.addWidget(self._section_label("Crystal 顶光"))
        self._top_light_buttons: dict[str, QRadioButton] = {}
        self._top_light_group = QButtonGroup(self)
        tl_col = QVBoxLayout()
        tl_col.setSpacing(4)
        for idx, (mode_id, label) in enumerate(LIGHT_MODES.items()):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._top_light_group.addButton(rb, idx)
            self._top_light_buttons[mode_id] = rb
            tl_col.addWidget(rb)
        crystal_l.addLayout(tl_col)
        self._top_light_buttons[DEFAULT_LIGHT_MODE].setChecked(True)
        self._top_light_label = QLabel()
        self._top_light_label.setObjectName("HintTextSmall")
        self._top_light_slider = QSlider(Qt.Horizontal)
        self._top_light_slider.setRange(0, SHADOW_STRENGTH_MAX)
        self._top_light_slider.setValue(DEFAULT_TOP_LIGHT_PEAK)
        self._top_light_slider.valueChanged.connect(self._update_top_light_label)
        row_tl = QHBoxLayout()
        row_tl.addWidget(QLabel("顶光强度"))
        row_tl.addWidget(self._top_light_slider, 1)
        row_tl.addWidget(self._top_light_label)
        crystal_l.addLayout(row_tl)
        layout.addWidget(self._crystal_light_section)

        self._qss_highlight_section = QWidget()
        qss_l = QVBoxLayout(self._qss_highlight_section)
        qss_l.setContentsMargins(0, 0, 0, 0)
        qss_l.setSpacing(6)
        qss_l.addWidget(self._section_label("QSS 页面高光"))
        self._qss_body_buttons: dict[str, QRadioButton] = {}
        self._qss_body_group = QButtonGroup(self)
        qb_col = QVBoxLayout()
        qb_col.setSpacing(4)
        for idx, (mode_id, label) in enumerate(QSS_BODY_MODES.items()):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._qss_body_group.addButton(rb, idx)
            self._qss_body_buttons[mode_id] = rb
            qb_col.addWidget(rb)
        qss_l.addLayout(qb_col)
        self._qss_body_buttons[DEFAULT_QSS_BODY].setChecked(True)
        self._qss_highlight_buttons: dict[str, QRadioButton] = {}
        self._qss_highlight_group = QButtonGroup(self)
        qh_col = QVBoxLayout()
        qh_col.setSpacing(4)
        for idx, (mode_id, label) in enumerate(QSS_HIGHLIGHT_MODES.items()):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._qss_highlight_group.addButton(rb, idx)
            self._qss_highlight_buttons[mode_id] = rb
            qh_col.addWidget(rb)
        qss_l.addLayout(qh_col)
        self._qss_highlight_buttons[DEFAULT_QSS_HIGHLIGHT].setChecked(True)
        self._qss_highlight_label = QLabel()
        self._qss_highlight_label.setObjectName("HintTextSmall")
        self._qss_highlight_slider = QSlider(Qt.Horizontal)
        self._qss_highlight_slider.setRange(0, SHADOW_STRENGTH_MAX)
        self._qss_highlight_slider.setValue(DEFAULT_QSS_HIGHLIGHT_PEAK)
        self._qss_highlight_slider.valueChanged.connect(self._update_qss_highlight_label)
        row_qh = QHBoxLayout()
        row_qh.addWidget(QLabel("高光强度"))
        row_qh.addWidget(self._qss_highlight_slider, 1)
        row_qh.addWidget(self._qss_highlight_label)
        qss_l.addLayout(row_qh)
        layout.addWidget(self._qss_highlight_section)

        self._update_medium_alpha_label(self._medium_alpha_slider.value())
        self._update_compact_alpha_label(self._compact_alpha_slider.value())
        self._update_font_size_label(self._font_size_slider.value())
        self._update_shadow_label(self._shadow_slider.value())
        self._update_top_light_label(self._top_light_slider.value())
        self._update_qss_highlight_label(self._qss_highlight_slider.value())
        self._update_luxury_star_label(self._luxury_star_slider.value())
        self.sync_theme_sections()

        save_row = QHBoxLayout()
        self._save_btn = QPushButton("保存并应用")
        self._save_btn.setObjectName("StepBtnPrimary")
        self._save_btn.clicked.connect(self.save_requested.emit)
        save_row.addWidget(self._save_btn)
        save_row.addStretch()
        layout.addLayout(save_row)

        self._feedback = QLabel("")
        self._feedback.setObjectName("HintTextSmall")
        self._feedback.setWordWrap(True)
        layout.addWidget(self._feedback)

    def set_feedback(self, text: str) -> None:
        self._feedback.setText(text)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("HintText")
        return lbl

    def _on_shell_style_clicked(self, button: QRadioButton) -> None:
        for style_id, rb in self._shell_style_buttons.items():
            if rb is button:
                recommended = default_crystal_shadow_strength(style_id)
                self._shadow_slider.blockSignals(True)
                self._shadow_slider.setValue(recommended)
                self._shadow_slider.blockSignals(False)
                self._update_shadow_label(recommended)
                self.shell_style_changed.emit(style_id)
                self.sync_mode_sections()
                break

    def _on_theme_clicked(self, _button: QRadioButton) -> None:
        self.sync_theme_sections()
        self._emit_preview_layout()

    def _on_luxury_bg_clicked(self, _button: QRadioButton) -> None:
        self._sync_luxury_star_slider()
        self._emit_preview()

    def _emit_preview(self, *_args) -> None:
        self.appearance_preview_requested.emit(self.current_appearance())

    def _emit_preview_layout(self, *_args) -> None:
        self.appearance_preview_requested.emit(self.current_appearance())
        QTimer.singleShot(0, self.preview_layout_changed.emit)

    def _current_luxury_bg(self) -> str:
        for mode_id, btn in self._luxury_bg_buttons.items():
            if btn.isChecked():
                return mode_id
        return DEFAULT_LUXURY_BG_MODE

    def _sync_luxury_star_slider(self) -> None:
        kraft = self._current_luxury_bg() == "kraft"
        self._luxury_star_slider.setEnabled(not kraft)
        self._luxury_star_hint.setVisible(kraft)

    def sync_theme_sections(self) -> None:
        luxury = self.current_theme() == LUXURY_THEME_ID
        for section in (
            self._classic_shell_section,
            self._classic_alpha_section,
            self._classic_shadow_section,
            self._classic_title_section,
            self._crystal_light_section,
            self._qss_highlight_section,
        ):
            section.setVisible(not luxury)
        self._luxury_section.setVisible(luxury)
        if luxury:
            self._sync_luxury_star_slider()
        else:
            self.sync_mode_sections()

    def _current_shell_style(self) -> str:
        for style_id, btn in self._shell_style_buttons.items():
            if btn.isChecked():
                return style_id
        return DEFAULT_SHELL_STYLE

    def sync_mode_sections(self) -> None:
        shell_style = self._current_shell_style()
        crystal = is_crystal_shell(shell_style)
        self._crystal_light_section.setVisible(crystal)
        self._qss_highlight_section.setVisible(not crystal)
        for btn in self._top_light_buttons.values():
            btn.setEnabled(crystal)
        self._top_light_slider.setEnabled(crystal)
        for btn in self._qss_body_buttons.values():
            btn.setEnabled(not crystal)
        for btn in self._qss_highlight_buttons.values():
            btn.setEnabled(not crystal)
        self._qss_highlight_slider.setEnabled(not crystal)

    def _update_medium_alpha_label(self, value: int) -> None:
        self._medium_alpha_label.setText(f"{value}%")

    def _update_compact_alpha_label(self, value: int) -> None:
        self._compact_alpha_label.setText(f"{value}%")

    def _update_font_size_label(self, value: int) -> None:
        self._font_size_label.setText(f"{value}px")

    def _update_shadow_label(self, value: int) -> None:
        self._shadow_label.setText(str(value))

    def _update_top_light_label(self, value: int) -> None:
        self._top_light_label.setText(str(value))

    def _update_qss_highlight_label(self, value: int) -> None:
        self._qss_highlight_label.setText(str(value))

    def _update_luxury_star_label(self, value: int) -> None:
        self._luxury_star_label.setText(str(value))

    def _checked_mode(self, buttons: dict[str, QRadioButton], default: str) -> str:
        for mode_id, btn in buttons.items():
            if btn.isChecked():
                return mode_id
        return default

    def current_theme(self) -> str:
        for theme_id, btn in self._theme_buttons.items():
            if btn.isChecked():
                return theme_id
        return "current"

    def set_theme(self, theme_id: str) -> None:
        btn = self._theme_buttons.get(theme_id)
        if btn is not None:
            btn.setChecked(True)

    def current_appearance(self) -> dict:
        shell_style = self._current_shell_style()
        return {
            "ui_theme": self.current_theme(),
            "shell_style": shell_style,
            "shell_alpha_medium": self._medium_alpha_slider.value(),
            "shell_alpha_compact": self._compact_alpha_slider.value(),
            "font_size": self._font_size_slider.value(),
            "crystal_shadow_strength": self._shadow_slider.value(),
            "title_art_mode": self._checked_mode(
                self._title_art_buttons, DEFAULT_TITLE_ART
            ),
            "top_light_mode": self._checked_mode(
                self._top_light_buttons, DEFAULT_LIGHT_MODE
            ),
            "top_light_peak": self._top_light_slider.value(),
            "qss_body_mode": self._checked_mode(
                self._qss_body_buttons, DEFAULT_QSS_BODY
            ),
            "qss_highlight_mode": self._checked_mode(
                self._qss_highlight_buttons, DEFAULT_QSS_HIGHLIGHT
            ),
            "qss_highlight_peak": self._qss_highlight_slider.value(),
            "luxury_bg_mode": self._current_luxury_bg(),
            "luxury_star_intensity": self._luxury_star_slider.value(),
            "luxury_script_font_id": self._checked_mode(
                self._luxury_font_buttons, DEFAULT_SCRIPT_FONT_ID
            ),
            "luxury_gold_mode": "dual_layer",
            "luxury_btn_mode": "hover",
        }

    def set_appearance(self, data: dict) -> None:
        shell_style = data.get("shell_style", DEFAULT_SHELL_STYLE)
        btn = self._shell_style_buttons.get(shell_style)
        if btn is not None:
            btn.setChecked(True)
        self.set_theme(data.get("ui_theme", "current"))
        self._medium_alpha_slider.setValue(
            int(data.get("shell_alpha_medium", DEFAULT_SHELL_ALPHA_MEDIUM))
        )
        self._compact_alpha_slider.setValue(
            int(data.get("shell_alpha_compact", DEFAULT_SHELL_ALPHA_COMPACT))
        )
        self._font_size_slider.setValue(int(data.get("font_size", DEFAULT_FONT_SIZE)))
        shadow = data.get("crystal_shadow_strength")
        if shadow is None:
            shadow = default_crystal_shadow_strength(shell_style)
        self._shadow_slider.setValue(int(shadow))
        title_art = data.get("title_art_mode", DEFAULT_TITLE_ART)
        btn_t = self._title_art_buttons.get(title_art)
        if btn_t is not None:
            btn_t.setChecked(True)
        top_light = data.get("top_light_mode", DEFAULT_LIGHT_MODE)
        btn_tl = self._top_light_buttons.get(top_light)
        if btn_tl is not None:
            btn_tl.setChecked(True)
        self._top_light_slider.setValue(int(data.get("top_light_peak", DEFAULT_TOP_LIGHT_PEAK)))
        qss_body = data.get("qss_body_mode", DEFAULT_QSS_BODY)
        btn_qb = self._qss_body_buttons.get(qss_body)
        if btn_qb is not None:
            btn_qb.setChecked(True)
        qss_hl = data.get("qss_highlight_mode", DEFAULT_QSS_HIGHLIGHT)
        btn_qh = self._qss_highlight_buttons.get(qss_hl)
        if btn_qh is not None:
            btn_qh.setChecked(True)
        self._qss_highlight_slider.setValue(
            int(data.get("qss_highlight_peak", DEFAULT_QSS_HIGHLIGHT_PEAK))
        )
        luxury_bg = data.get("luxury_bg_mode", DEFAULT_LUXURY_BG_MODE)
        btn_lb = self._luxury_bg_buttons.get(luxury_bg)
        if btn_lb is not None:
            btn_lb.setChecked(True)
        self._luxury_star_slider.setValue(
            int(data.get("luxury_star_intensity", DEFAULT_LUXURY_STAR_INTENSITY))
        )
        luxury_font = data.get("luxury_script_font_id", DEFAULT_SCRIPT_FONT_ID)
        btn_lf = self._luxury_font_buttons.get(luxury_font)
        if btn_lf is not None:
            btn_lf.setChecked(True)
        self.sync_theme_sections()


class UiThemeGroup(QFrame):
    theme_changed = pyqtSignal(str)

    _THEMES = (
        ("current", "默认（工程基线）"),
        ("variant_b", "变体 B"),
        ("variant_c", "变体 C"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("界面主题")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel("切换面板配色方案；变体 B/C 为 Stitch 设计占位，后续可替换为正式稿。")
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._buttons: dict[str, QRadioButton] = {}
        self._group = QButtonGroup(self)
        row = QVBoxLayout()
        row.setSpacing(6)
        for idx, (theme_id, label) in enumerate(self._THEMES):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._group.addButton(rb, idx)
            self._buttons[theme_id] = rb
            row.addWidget(rb)
        self._group.buttonClicked.connect(self._on_click)
        layout.addLayout(row)
        self._buttons["current"].setChecked(True)

    def _on_click(self):
        self.theme_changed.emit(self.current_theme())

    def current_theme(self) -> str:
        for theme_id, btn in self._buttons.items():
            if btn.isChecked():
                return theme_id
        return "current"

    def set_theme(self, theme_id: str) -> None:
        btn = self._buttons.get(theme_id)
        if btn is not None:
            btn.setChecked(True)
