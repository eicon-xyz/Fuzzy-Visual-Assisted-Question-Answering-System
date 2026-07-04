# HAJIMI UI 协作规范

本文档定义 **布局层** 与 **样式层** 的边界，供人工与 AI 改 UI 时遵守。

## 层级职责

| 层级 | 路径 | 允许 | 禁止 |
|------|------|------|------|
| **Layout** | `ui/native/medium_panel.py`（信号/页面）、`ui/native/layout/` | 控件树、stretch、objectName、信号 | 颜色、font-size、background、shadow |
| **Layout tokens** | `ui/native/layout_tokens.py` | 尺寸、间距、动画 ms | 十六进制色值 |
| **Style / Theme** | `ui/native/themes/` | QSS；壳可选 QPainter | `setContentsMargins`、改 widget 树 |
| **Visual tokens** | `ui/native/visual_tokens.py` | overlay / Python 绘制的颜色 | 布局数字 |
| **Shell renderer** | `ui/native/shell_renderer.py` | `#NativeShell` / `#CompactShell` 背景 | 顶栏内部样式 |

## 硬规则

1. `medium_panel.py` 内 **禁止** `setStyleSheet`；**禁止** `setFixedHeight` 等尺寸 unless 引用 `layout_tokens`。
2. `themes/*/topbar.qss` 内避免写会改变占位高度的属性（若必须，改 `layout_tokens` 并在本文档标注）。
3. **STYLE ONLY** 任务不得修改 `medium_panel.py`、`layout/`、`layout_tokens.py`。
4. **LAYOUT ONLY** 任务不得修改任何 `.qss` 文件。

## 主题包结构

```
ui/native/themes/
  _base.qss              # 导航、设置、对话框 — 三主题共享
  current/               # 工程默认槽（非设计定稿）
    shell.qss            # 改背景只动此文件
    topbar.qss
    content.qss
    shell_crystal.qss    # crystal 模式透明壳（与 QPainter 互斥）
  variant_b/             # Stitch 占位
  variant_c/
```

切换主题：`ThemeManager.apply(theme_id)` + `user_settings.ui_theme`。

Shell 模式 **互斥**：`qss`（QSS 实底 + shadow）与 `crystal`（透明 QSS + `paint_crystal_glass`）不可同时生效。

## AI 任务模板

### STYLE ONLY — 只改壳子背景

```text
【任务类型】STYLE ONLY — 只改 themes/current/shell.qss
【禁止】medium_panel.py, layout_tokens.py, topbar.qss, content.qss, layout/
【验收】顶栏截图与改前一致；仅 NativeShell / CompactShell 背景变化
```

### STYLE ONLY — 只改顶栏外观

```text
【任务类型】STYLE ONLY — 只改 themes/current/topbar.qss
【禁止】medium_panel.py, shell.qss, content.qss, layout/
【验收】壳子背景不变；仅 TopBar / TopTitle / StatusBadge 等顶栏样式变化
```

### LAYOUT ONLY — 只改顶栏排版

```text
【任务类型】LAYOUT ONLY — 只改 layout_tokens TOP_BAR_* + layout/topbar_layout.py
【禁止】任何 .qss 文件、themes/
【验收】颜色不变；顶栏高度/间距符合 layout_tokens 数值表
```

## 第三方库

- **PyQt-Fluent-Widgets**：不推荐整库替换（无边框自定义 UI 冲突）。
- **QDarkTheme**：不推荐（与现有 objectName QSS 打架）。

继续 **ThemeManager + 分包 QSS + layout_tokens** 路线；Stitch 稿只进 `themes/variant_*`。

## 运行环境与主题降级

| 场景 | 行为 | 建议 |
|------|------|------|
| 首次运行 | 默认 `ui_theme=current`（`user_settings.json` 未创建时） | 组员无需改主题即可跑通 |
| `variant_luxury` | 需要 `assets/fonts/` 下字体文件（已在 Git） | 缺字体时标题回退系统字体，不 crash |
| QtSvg 缺失 | `nav_icons` / `luxury/icons` 返回空图标，窗口仍可启动 | 正式环境请 `python scripts/check_ui_env.py` 通过后再交付 |
| QtSvg 完整 | 导航、托盘、Luxury 线稿图标正常显示 | `pip install --force-reinstall PyQt5` 可修复缺模块 |

配置默认值单源：[`core/defaults.py`](../core/defaults.py)（A 端 8010、本地 OmniParser 8002）。
