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
    QCheckBox,
    QStackedWidget,
    QFileDialog,
    QComboBox,
)

from ui.native.luxury.qss import DEFAULT_LUXURY_BTN_MODE, DEFAULT_LUXURY_GOLD_MODE
from ui.native.luxury.title import DEFAULT_SCRIPT_FONT_ID, script_font_labels
from ui.native.shell_appearance import (
    APPEARANCE_SCHEME_IDS,
    APPEARANCE_SCHEME_LABELS,
    DEFAULT_CRYSTAL_EDGE_SHADOW,
    DEFAULT_FONT_SIZE,
    DEFAULT_LUXURY_STAR_INTENSITY,
    DEFAULT_SHELL_ALPHA_COMPACT,
    DEFAULT_SHELL_ALPHA_MEDIUM,
    DEFAULT_SHELL_STYLE,
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    LUXURY_STAR_INTENSITY_MAX,
    SCHEME_DEFAULT_BLUE,
    SCHEME_ELEGANT_BLACK,
    SCHEME_KRAFT_PAPER,
    SCHEME_LUXURY_GOLD,
    SCHEME_ORANGE_CAT,
    SHADOW_STRENGTH_MAX,
    SHELL_ALPHA_MAX,
    SHELL_ALPHA_MIN,
    default_crystal_shadow_strength,
    scheme_to_settings,
    settings_to_scheme,
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
from ui.native.title_art import DEFAULT_TITLE_ART, TITLE_ART_MODES

_ORANGE_CAT_AVATAR_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"
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

    def __init__(self, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        if not embedded:
            self.setObjectName("Card")
        layout = QVBoxLayout(self)
        margins = (0, 0, 0, 0) if embedded else (16, 16, 16, 16)
        layout.setContentsMargins(*margins)
        layout.setSpacing(8)

        title = QLabel("部署模式")
        title.setObjectName("SectionTitle" if embedded else "SectionTitle")
        layout.addWidget(title)

        hint = QLabel(
            "GPU API（推荐）：本机 A 端 + SSH 隧道 :9800；"
            "本地 CPU：本机 OmniParser :8002 + A 端；"
            "内网 API：仅连远程 A 端（需校园网/VPN）"
        )
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._gpu_api = QRadioButton("GPU API（推荐）")
        self._gpu_api.setObjectName("SettingsRadio")
        self._local = QRadioButton("本地 CPU")
        self._local.setObjectName("SettingsRadio")
        self._intranet = QRadioButton("内网 API")
        self._intranet.setObjectName("SettingsRadio")
        self._gpu_api.setChecked(True)

        self._group = QButtonGroup(self)
        self._group.addButton(self._gpu_api, 0)
        self._group.addButton(self._local, 1)
        self._group.addButton(self._intranet, 2)
        self._group.buttonClicked.connect(self._on_click)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self._gpu_api)
        row.addWidget(self._local)
        row.addWidget(self._intranet)
        row.addStretch()
        layout.addLayout(row)

    def _on_click(self):
        self.mode_changed.emit(self.current_mode())

    def current_mode(self) -> str:
        if self._intranet.isChecked():
            return "intranet"
        if self._local.isChecked():
            return "local"
        return "gpu_api"

    def set_mode(self, mode: str) -> None:
        if mode == "intranet":
            self._intranet.setChecked(True)
        elif mode == "local":
            self._local.setChecked(True)
        else:
            self._gpu_api.setChecked(True)


class GuidanceRouteGroup(QFrame):
    """指引路由：显式 L4 / L3_DEFERRED / L3 / 自动。"""

    mode_changed = pyqtSignal(str)

    _MODES = (
        ("l5", "L5 自动执行（默认）", "A 端 Agent Loop 自动操作鼠标键盘；需首次知情确认"),
        ("fast", "L4 Vision 快路径", "跳过 OmniParser，Planner+Locator Vision，仅需 A 端+LLM"),
        ("balanced", "L3 逐步 Vision", "先文本规划，每步 Vision 定位，不需 OmniParser"),
        ("precision", "L3 OmniParser 精准", "全屏 UI 检测 + 元素绑定，需 GPU/CPU 检测服务"),
        ("auto", "自动选择（不含 L5）", "有截图时优先 L4，模板/浏览器等自动分流"),
    )

    def __init__(self, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        if not embedded:
            self.setObjectName("Card")
        layout = QVBoxLayout(self)
        margins = (0, 0, 0, 0) if embedded else (16, 16, 16, 16)
        layout.setContentsMargins(*margins)
        layout.setSpacing(8)

        title = QLabel("指引路由")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(
            "选择任务处理路径。默认 L5 为自动执行（会操作本机鼠标键盘）；"
            "仅需屏幕红框指引时选 L4/L3。"
        )
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._buttons: dict[str, QRadioButton] = {}
        self._group = QButtonGroup(self)
        for idx, (mode_id, label, _desc) in enumerate(self._MODES):
            rb = QRadioButton(label)
            rb.setObjectName("SettingsRadio")
            self._group.addButton(rb, idx)
            self._buttons[mode_id] = rb
            layout.addWidget(rb)
        self._buttons["l5"].setChecked(True)
        self._group.buttonClicked.connect(self._on_click)

        self._mode_hint = QLabel(self._MODES[0][2])
        self._mode_hint.setObjectName("HintTextSmall")
        self._mode_hint.setWordWrap(True)
        layout.addWidget(self._mode_hint)

    def _on_click(self):
        mode = self.current_mode()
        for mid, _label, desc in self._MODES:
            if mid == mode:
                self._mode_hint.setText(desc)
                break
        self.mode_changed.emit(mode)

    def current_mode(self) -> str:
        for mode_id, rb in self._buttons.items():
            if rb.isChecked():
                return mode_id
        return "l5"

    def set_mode(self, mode: str) -> None:
        target = mode if mode in self._buttons else "l5"
        self._buttons[target].setChecked(True)
        for mid, _label, desc in self._MODES:
            if mid == target:
                self._mode_hint.setText(desc)
                break


# 兼容旧引用
SpeedModeGroup = GuidanceRouteGroup


class L5ExecutionGroup(QFrame):
    """L5 自动执行：桌面标注与快捷键。"""

    def __init__(self, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        if not embedded:
            self.setObjectName("Card")
        layout = QVBoxLayout(self)
        margins = (0, 0, 0, 0) if embedded else (16, 16, 16, 16)
        layout.setContentsMargins(*margins)
        layout.setSpacing(8)

        title = QLabel("L5 自动执行")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        from PyQt5.QtWidgets import QCheckBox

        self._desktop_overlay = QCheckBox("L5 桌面标注（Agent 点击时在屏幕显示高亮）")
        self._desktop_overlay.setObjectName("SettingsCheck")
        self._desktop_overlay.setChecked(True)
        layout.addWidget(self._desktop_overlay)

        hint = QLabel(
            "关闭后仅在步骤面板内查看执行时间线与 SoM 缩略图。"
            "暂停/继续需 Sidecar 升级后可用。"
        )
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def set_values(self, data: dict) -> None:
        self._desktop_overlay.setChecked(bool(data.get("l5_desktop_overlay", True)))

    def get_values(self) -> dict:
        return {
            "l5_desktop_overlay": self._desktop_overlay.isChecked(),
        }


class L4VisionGroup(QFrame):
    """L4 Vision 快路径：Planner / Locator 模型与 Pipeline 开关。"""

    def __init__(self, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        if not embedded:
            self.setObjectName("Card")
        layout = QVBoxLayout(self)
        margins = (0, 0, 0, 0) if embedded else (16, 16, 16, 16)
        layout.setContentsMargins(*margins)
        layout.setSpacing(8)

        title = QLabel("L4 Vision")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(
            "快速路由下使用。Planner 默认纯文本规划；Locator 必须支持识图（Vision）。"
            "留空则 Planner 用 DeepSeek、Locator 用上方「问答模型名」。"
            "保存后写入 server/.env，本地/GPU 模式会自动重启 A 端。"
        )
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._field_planner = SettingsFieldRow(
            "L4 Planner 模型",
            "留空=DeepSeek，如 deepseek-chat",
        )
        self._field_locator = SettingsFieldRow(
            "L4 Locator 模型",
            "gpt-5.5（Vision 识图定位）",
        )
        layout.addWidget(self._field_planner)
        layout.addWidget(self._field_locator)

        self._planner_vision = QCheckBox("Planner 规划时也传截图（默认关，更省 token）")
        self._planner_vision.setObjectName("SettingsRadio")
        self._strict_locate = QCheckBox("Strict 定位：无坐标时自动重试一次")
        self._strict_locate.setObjectName("SettingsRadio")
        self._pipeline = QCheckBox("轻量 Pipeline：屏幕摘要 + UIA 窗口提示")
        self._pipeline.setObjectName("SettingsRadio")
        self._strict_locate.setChecked(True)
        self._pipeline.setChecked(True)

        for cb in (self._planner_vision, self._strict_locate, self._pipeline):
            layout.addWidget(cb)

    def set_values(self, data: dict) -> None:
        self._field_planner.set_text(data.get("planner_model", ""))
        self._field_locator.set_text(data.get("locator_model", ""))
        self._planner_vision.setChecked(bool(data.get("planner_use_vision")))
        self._strict_locate.setChecked(bool(data.get("strict_locate", True)))
        self._pipeline.setChecked(bool(data.get("pipeline_enabled", True)))

    def get_values(self) -> dict:
        return {
            "planner_model": self._field_planner.text(),
            "locator_model": self._field_locator.text(),
            "planner_use_vision": self._planner_vision.isChecked(),
            "strict_locate": self._strict_locate.isChecked(),
            "pipeline_enabled": self._pipeline.isChecked(),
        }

    def set_enabled(self, enabled: bool) -> None:
        self._field_planner.set_enabled(enabled)
        self._field_locator.set_enabled(enabled)
        self._planner_vision.setEnabled(enabled)
        self._strict_locate.setEnabled(enabled)
        self._pipeline.setEnabled(enabled)


class ModelSettingsGroup(QFrame):
    """部署 / 路由 / 模型 API / L4 — 单卡片 + 独立保存。"""

    model_save_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("模型设置")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        self.deployment = DeploymentModeGroup(embedded=True)
        layout.addWidget(self.deployment)

        self.guidance = GuidanceRouteGroup(embedded=True)
        layout.addWidget(self.guidance)

        self.l5_exec = L5ExecutionGroup(embedded=True)
        layout.addWidget(self.l5_exec)

        api_title = QLabel("模型 API")
        api_title.setObjectName("SectionTitle")
        layout.addWidget(api_title)

        from core.defaults import DEFAULT_OMNI_GPU_API_URL

        self.field_a_url = SettingsFieldRow("A 端地址", "http://127.0.0.1:8010")
        self.field_demo_key = SettingsFieldRow("Demo Key", "hajimi-demo-2026")
        self.field_llm_base = SettingsFieldRow(
            "问答 API Base", "https://www.daseinai.xyz/v1"
        )
        self.field_llm_key = SettingsFieldRow("问答 API Key", "", password=True)
        self.field_llm_model = SettingsFieldRow("问答模型名", "gpt-5.5")
        self.field_omni_url = SettingsFieldRow("OmniParser 地址", DEFAULT_OMNI_GPU_API_URL)
        self.field_omni_gpu = SettingsFieldRow(
            "OmniParser GPU", "可选，SSH 隧道端口如 http://127.0.0.1:8002"
        )
        for row in (
            self.field_a_url,
            self.field_demo_key,
            self.field_llm_base,
            self.field_llm_key,
            self.field_llm_model,
            self.field_omni_url,
            self.field_omni_gpu,
        ):
            layout.addWidget(row)

        self.l4 = L4VisionGroup(embedded=True)
        layout.addWidget(self.l4)

        save_row = QHBoxLayout()
        self._save_btn = QPushButton("保存并应用")
        self._save_btn.setObjectName("StepBtnPrimary")
        self._save_btn.clicked.connect(self.model_save_requested.emit)
        save_row.addWidget(self._save_btn)
        save_row.addStretch()
        layout.addLayout(save_row)

        self._feedback = QLabel("")
        self._feedback.setObjectName("HintTextSmall")
        self._feedback.setWordWrap(True)
        layout.addWidget(self._feedback)

    def set_feedback(self, text: str) -> None:
        self._feedback.setText(text)

    def settings_inputs(self) -> list:
        return [
            self.field_a_url.input,
            self.field_demo_key.input,
            self.field_llm_base.input,
            self.field_llm_key.input,
            self.field_llm_model.input,
            self.field_omni_url.input,
            self.field_omni_gpu.input,
            self.l4._field_planner.input,
            self.l4._field_locator.input,
        ]


class UiAppearanceGroup(QFrame):
    """主题外观：全局字号 + 配色方案 + 方案详细设置（实时预览）。"""

    shell_style_changed = pyqtSignal(str)
    save_requested = pyqtSignal()
    appearance_preview_requested = pyqtSignal(dict)
    preview_layout_changed = pyqtSignal()

    _SCHEME_STACK_INDEX = {
        SCHEME_DEFAULT_BLUE: 0,
        SCHEME_ELEGANT_BLACK: 1,
        SCHEME_LUXURY_GOLD: 2,
        SCHEME_KRAFT_PAPER: 3,
        SCHEME_ORANGE_CAT: 4,
    }

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
            "切换配色方案或详细项后可即时预览；点「保存并应用」写入磁盘并在下次启动保留。"
        )
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._font_size_label = QLabel()
        self._font_size_label.setObjectName("HintTextSmall")
        self._font_size_slider = QSlider(Qt.Horizontal)
        self._font_size_slider.setRange(FONT_SIZE_MIN, FONT_SIZE_MAX)
        self._font_size_slider.setValue(DEFAULT_FONT_SIZE)
        self._font_size_slider.valueChanged.connect(self._update_font_size_label)
        self._font_size_slider.valueChanged.connect(self._emit_preview)
        row_f = QHBoxLayout()
        row_f.addWidget(QLabel("全局字号"))
        row_f.addWidget(self._font_size_slider, 1)
        row_f.addWidget(self._font_size_label)
        layout.addLayout(row_f)

        layout.addWidget(self._section_label("配色方案"))
        self._scheme_buttons: dict[str, QRadioButton] = {}
        self._scheme_group = QButtonGroup(self)
        scheme_col = QVBoxLayout()
        scheme_col.setSpacing(4)
        for idx, scheme_id in enumerate(APPEARANCE_SCHEME_IDS):
            rb = QRadioButton(APPEARANCE_SCHEME_LABELS[scheme_id])
            rb.setObjectName("SettingsRadio")
            self._scheme_group.addButton(rb, idx)
            self._scheme_buttons[scheme_id] = rb
            scheme_col.addWidget(rb)
        layout.addLayout(scheme_col)
        self._scheme_buttons[SCHEME_DEFAULT_BLUE].setChecked(True)
        self._scheme_group.buttonClicked.connect(self._on_scheme_clicked)

        self._shell_style_buttons: dict[str, QRadioButton] = {}

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
        self._medium_alpha_slider.valueChanged.connect(self._emit_preview)
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
        self._compact_alpha_slider.valueChanged.connect(self._emit_preview)
        row_c = QHBoxLayout()
        row_c.addWidget(QLabel("小窗透明度"))
        row_c.addWidget(self._compact_alpha_slider, 1)
        row_c.addWidget(self._compact_alpha_label)
        classic_alpha_l.addLayout(row_c)

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
        self._shadow_slider.valueChanged.connect(self._emit_preview)
        row_s = QHBoxLayout()
        row_s.addWidget(QLabel("Crystal 阴影"))
        row_s.addWidget(self._shadow_slider, 1)
        row_s.addWidget(self._shadow_label)
        classic_shadow_l.addLayout(row_s)
        shadow_hint = QLabel("纯细边建议 0，极轻阴影建议 14。")
        shadow_hint.setObjectName("HintTextSmall")
        shadow_hint.setWordWrap(True)
        classic_shadow_l.addWidget(shadow_hint)

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
        self._title_art_group.buttonClicked.connect(self._emit_preview)

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
        self._luxury_star_section.toggled.connect(self._emit_preview_layout)
        self._luxury_font_section.toggled.connect(self._emit_preview_layout)

        self._orange_cat_section = QWidget()
        orange_l = QVBoxLayout(self._orange_cat_section)
        orange_l.setContentsMargins(0, 0, 0, 0)
        orange_l.setSpacing(6)
        orange_l.addWidget(self._section_label("详细设置"))
        orange_hint = QLabel(
            "清新近白 · 玻璃顶栏 · 渐变标题。留空 splash 音效则使用默认 start.mp3。"
        )
        orange_hint.setObjectName("HintTextSmall")
        orange_hint.setWordWrap(True)
        orange_l.addWidget(orange_hint)
        self._orange_cat_sound_edit = QLineEdit()
        self._orange_cat_sound_edit.setObjectName("SettingsInput")
        self._orange_cat_sound_edit.setPlaceholderText("splash 音效路径（可选）")
        self._orange_cat_sound_edit.textChanged.connect(self._emit_preview)
        orange_l.addWidget(self._orange_cat_sound_edit)

        self._orange_cat_ai_avatar_edit = QLineEdit()
        self._orange_cat_ai_avatar_edit.setObjectName("SettingsInput")
        self._orange_cat_ai_avatar_edit.setPlaceholderText("AI 对话头像（可选）")
        self._orange_cat_ai_avatar_edit.textChanged.connect(self._emit_preview)
        orange_l.addLayout(
            self._orange_avatar_row(
                "AI 头像",
                self._orange_cat_ai_avatar_edit,
                self._pick_orange_cat_ai_avatar,
                self._clear_orange_cat_ai_avatar,
            )
        )

        self._orange_cat_user_avatar_edit = QLineEdit()
        self._orange_cat_user_avatar_edit.setObjectName("SettingsInput")
        self._orange_cat_user_avatar_edit.setPlaceholderText("用户对话头像（可选）")
        self._orange_cat_user_avatar_edit.textChanged.connect(self._emit_preview)
        orange_l.addLayout(
            self._orange_avatar_row(
                "用户头像",
                self._orange_cat_user_avatar_edit,
                self._pick_orange_cat_user_avatar,
                self._clear_orange_cat_user_avatar,
            )
        )

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
        self._top_light_group.buttonClicked.connect(self._emit_preview)
        self._top_light_label = QLabel()
        self._top_light_label.setObjectName("HintTextSmall")
        self._top_light_slider = QSlider(Qt.Horizontal)
        self._top_light_slider.setRange(0, SHADOW_STRENGTH_MAX)
        self._top_light_slider.setValue(DEFAULT_TOP_LIGHT_PEAK)
        self._top_light_slider.valueChanged.connect(self._update_top_light_label)
        self._top_light_slider.valueChanged.connect(self._emit_preview)
        row_tl = QHBoxLayout()
        row_tl.addWidget(QLabel("顶光强度"))
        row_tl.addWidget(self._top_light_slider, 1)
        row_tl.addWidget(self._top_light_label)
        crystal_l.addLayout(row_tl)

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
        self._qss_body_group.buttonClicked.connect(self._emit_preview)
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
        self._qss_highlight_group.buttonClicked.connect(self._emit_preview)
        self._qss_highlight_label = QLabel()
        self._qss_highlight_label.setObjectName("HintTextSmall")
        self._qss_highlight_slider = QSlider(Qt.Horizontal)
        self._qss_highlight_slider.setRange(0, SHADOW_STRENGTH_MAX)
        self._qss_highlight_slider.setValue(DEFAULT_QSS_HIGHLIGHT_PEAK)
        self._qss_highlight_slider.valueChanged.connect(self._update_qss_highlight_label)
        self._qss_highlight_slider.valueChanged.connect(self._emit_preview)
        row_qh = QHBoxLayout()
        row_qh.addWidget(QLabel("高光强度"))
        row_qh.addWidget(self._qss_highlight_slider, 1)
        row_qh.addWidget(self._qss_highlight_label)
        qss_l.addLayout(row_qh)

        self._detail_stack = QStackedWidget()
        page_default = QWidget()
        self._default_detail_layout = QVBoxLayout(page_default)
        self._default_detail_layout.setContentsMargins(0, 0, 0, 0)
        self._default_detail_layout.setSpacing(6)
        self._default_detail_layout.addWidget(self._classic_title_section)
        self._default_detail_layout.addWidget(self._qss_highlight_section)
        self._detail_stack.addWidget(page_default)

        page_elegant = QWidget()
        self._elegant_detail_layout = QVBoxLayout(page_elegant)
        self._elegant_detail_layout.setContentsMargins(0, 0, 0, 0)
        self._elegant_detail_layout.setSpacing(6)
        self._elegant_detail_layout.addWidget(self._classic_shadow_section)
        self._elegant_detail_layout.addWidget(self._crystal_light_section)
        self._detail_stack.addWidget(page_elegant)

        page_luxury = QWidget()
        self._luxury_detail_layout = QVBoxLayout(page_luxury)
        self._luxury_detail_layout.setContentsMargins(0, 0, 0, 0)
        self._luxury_detail_layout.setSpacing(6)
        self._luxury_detail_layout.addWidget(self._luxury_star_section)
        self._luxury_font_anchor = QWidget()
        self._luxury_font_anchor_layout = QVBoxLayout(self._luxury_font_anchor)
        self._luxury_font_anchor_layout.setContentsMargins(0, 0, 0, 0)
        self._luxury_font_anchor_layout.addWidget(self._luxury_font_section)
        self._luxury_detail_layout.addWidget(self._luxury_font_anchor)
        self._detail_stack.addWidget(page_luxury)

        page_kraft = QWidget()
        p3 = QVBoxLayout(page_kraft)
        p3.setContentsMargins(0, 0, 0, 0)
        p3.setSpacing(6)
        kraft_hint = QLabel("牛皮纸底不使用星空。")
        kraft_hint.setObjectName("HintTextSmall")
        kraft_hint.setWordWrap(True)
        p3.addWidget(kraft_hint)
        self._kraft_font_host = QWidget()
        self._kraft_font_host_layout = QVBoxLayout(self._kraft_font_host)
        self._kraft_font_host_layout.setContentsMargins(0, 0, 0, 0)
        p3.addWidget(self._kraft_font_host)
        self._detail_stack.addWidget(page_kraft)

        page_orange = QWidget()
        self._orange_detail_layout = QVBoxLayout(page_orange)
        self._orange_detail_layout.setContentsMargins(0, 0, 0, 0)
        self._orange_detail_layout.setSpacing(6)
        self._orange_detail_layout.addWidget(self._orange_cat_section)
        self._detail_stack.addWidget(page_orange)

        layout.addWidget(self._detail_stack)

        self._update_medium_alpha_label(self._medium_alpha_slider.value())
        self._update_compact_alpha_label(self._compact_alpha_slider.value())
        self._update_font_size_label(self._font_size_slider.value())
        self._update_shadow_label(self._shadow_slider.value())
        self._update_top_light_label(self._top_light_slider.value())
        self._update_qss_highlight_label(self._qss_highlight_slider.value())
        self._update_luxury_star_label(self._luxury_star_slider.value())
        self.sync_scheme_sections()

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

    def _on_scheme_clicked(self, _button: QRadioButton) -> None:
        scheme = self.current_scheme()
        if scheme == SCHEME_ELEGANT_BLACK:
            self._shadow_slider.blockSignals(True)
            self._shadow_slider.setValue(DEFAULT_CRYSTAL_EDGE_SHADOW)
            self._shadow_slider.blockSignals(False)
            self._update_shadow_label(DEFAULT_CRYSTAL_EDGE_SHADOW)
        self.sync_scheme_sections()
        self._emit_preview_layout()

    def _emit_preview(self, *_args) -> None:
        self.appearance_preview_requested.emit(self.current_appearance())

    def _emit_preview_layout(self, *_args) -> None:
        self.appearance_preview_requested.emit(self.current_appearance())
        QTimer.singleShot(0, self.preview_layout_changed.emit)

    def sync_scheme_sections(self) -> None:
        scheme = self.current_scheme()
        index = self._SCHEME_STACK_INDEX.get(scheme, 0)
        self._detail_stack.setCurrentIndex(index)
        self._luxury_star_section.setVisible(scheme == SCHEME_LUXURY_GOLD)
        if scheme == SCHEME_KRAFT_PAPER:
            self._reparent_widget(self._luxury_font_section, self._kraft_font_host_layout)
        else:
            self._reparent_widget(self._luxury_font_section, self._luxury_font_anchor_layout)
        if scheme in (SCHEME_DEFAULT_BLUE, SCHEME_ELEGANT_BLACK, SCHEME_ORANGE_CAT):
            self._classic_alpha_section.show()
            if scheme == SCHEME_ORANGE_CAT:
                self._reparent_widget(self._classic_alpha_section, self._orange_detail_layout, 0)
            elif scheme == SCHEME_ELEGANT_BLACK:
                self._reparent_widget(self._classic_alpha_section, self._elegant_detail_layout, 0)
            else:
                self._reparent_widget(self._classic_alpha_section, self._default_detail_layout, 0)
        else:
            parent = self._classic_alpha_section.parentWidget()
            if parent is not None and parent.layout() is not None:
                parent.layout().removeWidget(self._classic_alpha_section)
            self._classic_alpha_section.setParent(self)
            self._classic_alpha_section.hide()

    @staticmethod
    def _reparent_widget(widget: QWidget, layout: QVBoxLayout, index: int | None = None) -> None:
        parent = widget.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().removeWidget(widget)
        if index is None:
            layout.addWidget(widget)
        else:
            layout.insertWidget(index, widget)

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

    def current_scheme(self) -> str:
        for scheme_id, btn in self._scheme_buttons.items():
            if btn.isChecked():
                return scheme_id
        return SCHEME_DEFAULT_BLUE

    def current_theme(self) -> str:
        return self.current_appearance().get("ui_theme", "current")

    def set_scheme(self, scheme_id: str) -> None:
        btn = self._scheme_buttons.get(scheme_id)
        if btn is not None:
            btn.setChecked(True)

    def set_theme(self, theme_id: str) -> None:
        """Legacy hook — map ui_theme + luxury bg to appearance scheme."""
        data = {"ui_theme": theme_id}
        if theme_id == "variant_luxury":
            data["luxury_bg_mode"] = "frosted"
        self.set_scheme(settings_to_scheme(data))

    def current_appearance(self) -> dict:
        scheme = self.current_scheme()
        data = scheme_to_settings(scheme)
        data["font_size"] = self._font_size_slider.value()
        data["shell_alpha_medium"] = self._medium_alpha_slider.value()
        data["shell_alpha_compact"] = self._compact_alpha_slider.value()
        data["crystal_shadow_strength"] = self._shadow_slider.value()
        data["title_art_mode"] = self._checked_mode(
            self._title_art_buttons, DEFAULT_TITLE_ART
        )
        data["top_light_mode"] = self._checked_mode(
            self._top_light_buttons, DEFAULT_LIGHT_MODE
        )
        data["top_light_peak"] = self._top_light_slider.value()
        data["qss_body_mode"] = self._checked_mode(
            self._qss_body_buttons, DEFAULT_QSS_BODY
        )
        data["qss_highlight_mode"] = self._checked_mode(
            self._qss_highlight_buttons, DEFAULT_QSS_HIGHLIGHT
        )
        data["qss_highlight_peak"] = self._qss_highlight_slider.value()
        data["luxury_star_intensity"] = self._luxury_star_slider.value()
        data["luxury_script_font_id"] = self._checked_mode(
            self._luxury_font_buttons, DEFAULT_SCRIPT_FONT_ID
        )
        data["luxury_gold_mode"] = "dual_layer"
        data["luxury_btn_mode"] = "hover"
        data["orange_cat_splash_audio"] = self._orange_cat_sound_edit.text().strip()
        data["orange_cat_ai_avatar"] = self._orange_cat_ai_avatar_edit.text().strip()
        data["orange_cat_user_avatar"] = self._orange_cat_user_avatar_edit.text().strip()
        return data

    def set_appearance(self, data: dict) -> None:
        scheme = settings_to_scheme(data)
        self.set_scheme(scheme)
        self._font_size_slider.setValue(int(data.get("font_size", DEFAULT_FONT_SIZE)))
        self._medium_alpha_slider.setValue(
            int(data.get("shell_alpha_medium", DEFAULT_SHELL_ALPHA_MEDIUM))
        )
        self._compact_alpha_slider.setValue(
            int(data.get("shell_alpha_compact", DEFAULT_SHELL_ALPHA_COMPACT))
        )
        shell_style = data.get("shell_style", DEFAULT_SHELL_STYLE)
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
        self._luxury_star_slider.setValue(
            int(data.get("luxury_star_intensity", DEFAULT_LUXURY_STAR_INTENSITY))
        )
        luxury_font = data.get("luxury_script_font_id", DEFAULT_SCRIPT_FONT_ID)
        btn_lf = self._luxury_font_buttons.get(luxury_font)
        if btn_lf is not None:
            btn_lf.setChecked(True)
        self._orange_cat_sound_edit.setText(
            str(data.get("orange_cat_splash_audio", "") or "")
        )
        self._orange_cat_ai_avatar_edit.setText(
            str(data.get("orange_cat_ai_avatar", "") or "")
        )
        self._orange_cat_user_avatar_edit.setText(
            str(data.get("orange_cat_user_avatar", "") or "")
        )
        self.sync_scheme_sections()

    @staticmethod
    def _orange_avatar_row(
        label: str,
        edit: QLineEdit,
        pick_fn,
        clear_fn,
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setObjectName("HintText")
        row.addWidget(lbl)
        row.addWidget(edit, 1)
        browse = QPushButton("浏览")
        browse.setObjectName("StepBtn")
        browse.clicked.connect(pick_fn)
        clear_btn = QPushButton("清除")
        clear_btn.setObjectName("StepBtn")
        clear_btn.clicked.connect(clear_fn)
        row.addWidget(browse)
        row.addWidget(clear_btn)
        return row

    def _pick_orange_cat_ai_avatar(self) -> None:
        from ui.native.orange_cat.image_pool import user_folder

        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 AI 对话头像",
            user_folder() or "",
            _ORANGE_CAT_AVATAR_FILTER,
        )
        if path:
            self._orange_cat_ai_avatar_edit.setText(path)
            self._emit_preview()

    def _pick_orange_cat_user_avatar(self) -> None:
        from ui.native.orange_cat.image_pool import user_folder

        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择用户对话头像",
            user_folder() or "",
            _ORANGE_CAT_AVATAR_FILTER,
        )
        if path:
            self._orange_cat_user_avatar_edit.setText(path)
            self._emit_preview()

    def _clear_orange_cat_ai_avatar(self) -> None:
        self._orange_cat_ai_avatar_edit.clear()
        self._emit_preview()

    def _clear_orange_cat_user_avatar(self) -> None:
        self._orange_cat_user_avatar_edit.clear()
        self._emit_preview()


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


class VoiceSettingsGroup(QFrame):
    """语音 ASR/TTS 设置 — 独立保存（第三块）。"""

    voice_save_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("语音设置")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        hint = QLabel("控制麦克风识别与步骤语音播报；保存后 C 集成模块即时读取。")
        hint.setObjectName("HintTextSmall")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._tts_enabled = QCheckBox("启用 TTS 语音播报")
        self._tts_enabled.setObjectName("SettingsCheck")
        self._tts_enabled.setChecked(True)
        layout.addWidget(self._tts_enabled)

        self._asr_enabled = QCheckBox("启用 ASR 语音识别")
        self._asr_enabled.setObjectName("SettingsCheck")
        self._asr_enabled.setChecked(True)
        layout.addWidget(self._asr_enabled)

        speed_row = QHBoxLayout()
        speed_lbl = QLabel("TTS 语速")
        speed_lbl.setObjectName("SetRowLabel")
        speed_lbl.setMinimumWidth(120)
        self._tts_speed = QSlider(Qt.Horizontal)
        self._tts_speed.setObjectName("SettingsSlider")
        self._tts_speed.setMinimum(50)
        self._tts_speed.setMaximum(150)
        self._tts_speed.setValue(85)
        self._speed_value_lbl = QLabel("0.85")
        self._speed_value_lbl.setObjectName("HintTextSmall")
        self._tts_speed.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(speed_lbl)
        speed_row.addWidget(self._tts_speed, 1)
        speed_row.addWidget(self._speed_value_lbl)
        layout.addLayout(speed_row)

        tts_engine_row = QHBoxLayout()
        tts_engine_lbl = QLabel("TTS 引擎")
        tts_engine_lbl.setObjectName("SetRowLabel")
        tts_engine_lbl.setMinimumWidth(120)
        self._tts_engine = QComboBox()
        self._tts_engine.setObjectName("SettingsCombo")
        self._tts_engine.addItems(["pyttsx3", "azure", "baidu"])
        tts_engine_row.addWidget(tts_engine_lbl)
        tts_engine_row.addWidget(self._tts_engine, 1)
        layout.addLayout(tts_engine_row)

        asr_engine_row = QHBoxLayout()
        asr_engine_lbl = QLabel("ASR 引擎")
        asr_engine_lbl.setObjectName("SetRowLabel")
        asr_engine_lbl.setMinimumWidth(120)
        self._asr_engine = QComboBox()
        self._asr_engine.setObjectName("SettingsCombo")
        self._asr_engine.addItems(["vosk", "baidu", "google"])
        asr_engine_row.addWidget(asr_engine_lbl)
        asr_engine_row.addWidget(self._asr_engine, 1)
        layout.addLayout(asr_engine_row)

        save_row = QHBoxLayout()
        self._save_btn = QPushButton("保存并应用")
        self._save_btn.setObjectName("StepBtnPrimary")
        self._save_btn.clicked.connect(self.voice_save_requested.emit)
        save_row.addWidget(self._save_btn)
        save_row.addStretch()
        layout.addLayout(save_row)

        self._feedback = QLabel("")
        self._feedback.setObjectName("HintTextSmall")
        self._feedback.setWordWrap(True)
        layout.addWidget(self._feedback)

    def _on_speed_changed(self, value: int) -> None:
        self._speed_value_lbl.setText(f"{value / 100:.2f}")

    def set_feedback(self, text: str) -> None:
        self._feedback.setText(text)

    def current_voice(self) -> dict:
        return {
            "tts_enabled": self._tts_enabled.isChecked(),
            "asr_enabled": self._asr_enabled.isChecked(),
            "tts_speed": round(self._tts_speed.value() / 100.0, 2),
            "tts_engine": self._tts_engine.currentText(),
            "asr_engine": self._asr_engine.currentText(),
            "asr_language": "zh-CN",
        }

    def set_voice(self, data: dict) -> None:
        voice = data.get("voice") if "voice" in data else data
        if not isinstance(voice, dict):
            return
        self._tts_enabled.setChecked(bool(voice.get("tts_enabled", True)))
        self._asr_enabled.setChecked(bool(voice.get("asr_enabled", True)))
        speed = float(voice.get("tts_speed", 0.85))
        self._tts_speed.setValue(max(50, min(150, int(speed * 100))))
        tts_engine = voice.get("tts_engine", "pyttsx3")
        idx = self._tts_engine.findText(str(tts_engine))
        if idx >= 0:
            self._tts_engine.setCurrentIndex(idx)
        asr_engine = voice.get("asr_engine", "vosk")
        idx = self._asr_engine.findText(str(asr_engine))
        if idx >= 0:
            self._asr_engine.setCurrentIndex(idx)
