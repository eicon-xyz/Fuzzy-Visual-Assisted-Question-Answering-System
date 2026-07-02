"""系统设置页可复用控件。"""
from __future__ import annotations

from PyQt5.QtCore import Qt, QObject, QEvent, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QFrame,
    QSlider,
)

from ui.native.shell_appearance import (
    DEFAULT_CRYSTAL_EDGE_SHADOW,
    DEFAULT_CRYSTAL_LIGHT_SHADOW,
    DEFAULT_FONT_SIZE,
    DEFAULT_SHELL_ALPHA_COMPACT,
    DEFAULT_SHELL_ALPHA_MEDIUM,
    DEFAULT_SHELL_STYLE,
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    SHADOW_STRENGTH_MAX,
    SHELL_ALPHA_MAX,
    SHELL_ALPHA_MIN,
    SHELL_STYLES,
    default_crystal_shadow_strength,
)
from ui.native.theme_manager import THEME_LABELS


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
            "面板风格与配色在保存后生效；Crystal 阴影仅 Crystal 风格下可见。"
        )
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(self._section_label("面板风格"))
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
        layout.addLayout(shell_col)
        self._shell_style_buttons[DEFAULT_SHELL_STYLE].setChecked(True)

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
        layout.addLayout(row_m)

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
        layout.addLayout(row_c)

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
        layout.addLayout(row_s)

        shadow_hint = QLabel(
            "纯细边建议 0，极轻阴影建议 14；仅 Crystal 面板风格生效。"
        )
        shadow_hint.setObjectName("HintTextSmall")
        shadow_hint.setWordWrap(True)
        layout.addWidget(shadow_hint)

        self._update_medium_alpha_label(self._medium_alpha_slider.value())
        self._update_compact_alpha_label(self._compact_alpha_slider.value())
        self._update_font_size_label(self._font_size_slider.value())
        self._update_shadow_label(self._shadow_slider.value())

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
                break

    def _update_medium_alpha_label(self, value: int) -> None:
        self._medium_alpha_label.setText(f"{value}%")

    def _update_compact_alpha_label(self, value: int) -> None:
        self._compact_alpha_label.setText(f"{value}%")

    def _update_font_size_label(self, value: int) -> None:
        self._font_size_label.setText(f"{value}px")

    def _update_shadow_label(self, value: int) -> None:
        self._shadow_label.setText(str(value))

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
        shell_style = DEFAULT_SHELL_STYLE
        for style_id, btn in self._shell_style_buttons.items():
            if btn.isChecked():
                shell_style = style_id
                break
        return {
            "ui_theme": self.current_theme(),
            "shell_style": shell_style,
            "shell_alpha_medium": self._medium_alpha_slider.value(),
            "shell_alpha_compact": self._compact_alpha_slider.value(),
            "font_size": self._font_size_slider.value(),
            "crystal_shadow_strength": self._shadow_slider.value(),
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
