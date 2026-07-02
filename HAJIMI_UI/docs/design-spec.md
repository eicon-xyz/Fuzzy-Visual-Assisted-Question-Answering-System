# HAJIMI UI Design Spec

**Design canon (read-only):** [`ui/web/index.html`](../ui/web/index.html) — see also [`docs/ui-html-spec.md`](ui-html-spec.md).

**Native implementation:** [`ui/native/`](../ui/native/) + [`layout_tokens.py`](../ui/native/layout_tokens.py) + [`visual_tokens.py`](../ui/native/visual_tokens.py) + [`themes/`](../ui/native/themes/) via [`theme_manager.py`](../ui/native/theme_manager.py).

**Layout vs Style:** See [`docs/UI协作规范.md`](UI协作规范.md).

## Rollback

| Method | Command |
|--------|---------|
| WebEngine HTML UI | `set HAJIMI_NATIVE_UI=0` then `python main.py` |
| Browser demo | `python -m ui.web_preview` |
| **水晶玻璃风观感 Demo** | `python -m ui.style_preview_demo` — 左 320×496 + 右控制台，壳底色/α/字号/QSS·Crystal（设计试验） |
| Git native only | `git checkout main -- ui/native/` |
| Verify fallback | `scripts\verify_web_ui_fallback.bat` |

Shell backgrounds (default `qss` profile): `#NativeShell` / `#CompactShell` in `themes/*/shell.qss` + `apply_shell_shadow`. Optional `crystal` profile: transparent shell QSS + [`crystal_glass.py`](../ui/native/crystal_glass.py) via [`shell_renderer.py`](../ui/native/shell_renderer.py) — **mutually exclusive**. Child chrome transparent; bubbles + `InputFloat` keep distinct fill. Resize guides: [`resize_grip.py`](../ui/native/resize_grip.py).

## Layout vs Style boundary

| Layer | Files | Changes when… |
|-------|-------|----------------|
| Layout | `layout_tokens.py`, `layout/topbar_layout.py`, `medium_panel.py` | Resizing top bar, margins, widget tree |
| Style | `themes/*/shell.qss`, `topbar.qss`, `content.qss` | Colors, fonts, borders, shell gradient |
| Themes | `current`, `variant_b`, `variant_c` + `user_settings.ui_theme` | Switching skin in Settings |

`theme_current` = **engineering default slot**, not design approval. Visual target: [`ui/web/index.html`](../ui/web/index.html) or Stitch variants B/C.

## Style preview demo (design iteration)

Layout: **680×496** window — left **320×496** medium (1:1 logical px on busy desktop), right scrollable control panel. Compact **280×48** preview in control panel.

**定稿参数（Demo 确认）：** 320×496 medium · 280×48 compact · font **12px** · title **13px** · accent **#7c8fd4** · base **#0f172a** · processing **呼吸灯 pulse** · scrollbar **hover 提亮（Q14-A）** · Crystal shadow **极轻 1–2 层（Q13-B）**.

Shell console: **QSS 实底** / **Crystal · 纯细边** / **Crystal · 极轻阴影** — compare before locking production `THEME_PROFILES`.

Controls: accent A/B/C, shell three presets, **QSS 页面高光**（实底 solid/vertical_grad · 高光 pro/band/dual-lite · peak 0–60 默认 34）, **Crystal 顶光**（pro/dual/crystal · peak 默认 45 不变）, base color A/B/C, medium/compact alpha sliders (0.80–0.95), simulate processing.

**生产设置（`python main.py` → 系统设置 → 主题外观）：** 面板风格 QSS/Crystal 三档 + 配色变体 B/C + 中/小窗透明度 80–95% + 全局字号 11–15 + Crystal 阴影 0–60；保存并应用后写入 `%LOCALAPPDATA%/HAJIMI/user_settings.json`（`shell_style`, `shell_alpha_medium`, `shell_alpha_compact`, `font_size`, `crystal_shadow_strength`, `ui_theme`）。艺术字 / 顶光试验 / QSS 页面高光 **仍仅 Demo**。

```bash
python -m ui.style_preview_demo
```

Source: [`ui/style_preview_demo.py`](../ui/style_preview_demo.py). Production dimensions remain **480×520** until demo sign-off and separate size PR.

**顶栏标题（Round 8.1）：** 艺术字 `TitleArtWidget` **仅 Demo**；第一行 HAJIMI 三档（渐变 / Logo+渐变 / 展示字体），第二行 `TopSub` 固定「操作指引」。生产端仍为 [`topbar_layout.py`](../ui/native/layout/topbar_layout.py) 的 `QLabel#TopTitle` + `QLabel#TopSub`（随面板切换文案），艺术字上生产待单独 PR。

### Round 9 · QSS 实底 · 页面玻璃高光（Demo 定稿试验）

**范围：** 仅 `ui/style_preview_demo.py` + 本文档；**不改** `crystal_glass.py` / `shell_renderer.py` / `themes/current/` / `medium_panel.py`。

| ID | 主题 | 定稿 |
|----|------|------|
| Q34 | QSS 高光方案 | A pro / B band / C dual-lite — 控制台单选对比 |
| Q35 | 默认强度 | 滑条 0–60，**默认 34**（QSS 专用；Crystal 顶光默认 **45** 不动） |
| Q36 | 实底本体 | A 纯实底 solid / B 竖渐变 vertical_grad |
| Q37 | 控制台 | 独立区「QSS 页面高光」，与 Crystal 顶光互不覆盖 |
| Q38 | 范围 | Demo + spec 记录；生产迁移待「上生产」 |

**QSS 页面高光定稿候选（肉眼确认后锁定）：**

- 实底默认：**solid**（与生产 `shell.qss` rgba 观感一致）
- 高光默认：**dual-lite @ peak 34**（最接近 Crystal dual@34，但无 crystal 暗色渐变底）

**Crystal 用户偏好（生产候选，Demo 默认不变）：**

- 顶光：**dual** + peak **34**（用户主观偏好；Demo 仍保留 `DEFAULT_TOP_LIGHT_PEAK=45` 以便 A/B/C 对比）

### Round 10 · Crystal 阴影强度滑条（Demo 试验）

**范围：** 仅 `ui/style_preview_demo.py` + 本文档。

- 外阴影由 Demo 专用 `QGraphicsDropShadowEffect` 驱动（**不再**用 painter `_draw_rounded_shadow_light`，避免裁剪/不可见）
- 控制台 **阴影强度** 滑条 **0–60**；Crystal 两档均可调
- 预设默认：**纯细边 → 0**（无外晕）；**极轻阴影 → 14**（Q13-B 等效：≈ blur 14 / offset 3 / alpha ~28）
- QSS 实底仍用 `apply_shell_shadow`（blur 40, alpha 110），不受此滑条影响

**生产迁移备忘（非本次）：**

- `shadow_strength` token + DropShadow 参数迁入 theme system
- `paint_demo_qss_shell` + token 迁入 theme system（`shell_profile`: `highlight_mode`, `peak`, `body_mode`）
- 设置页 / config：`theme=qss_glass | crystal` 双 preset 并存

## Token mapping

| HTML `:root` | `layout_tokens.py` / `visual_tokens.py` | QSS / usage |
|--------------|-------------------|-------------|
| `--bg-primary` | `BG_PRIMARY` | shell backgrounds |
| `--glass-fill` | `GLASS_FILL` | `#NativeShell`, `#CompactShell` |
| `--glass-border` | `GLASS_BORDER` | shell border |
| `--accent` | `ACCENT` | buttons, nav active, user bubble |
| `--danger` | `DANGER` | overlay highlight, danger bubble |
| `--success` | `SUCCESS` | status executing, step done |
| `--warning` | `WARNING` | suspension dialog |
| `--text-primary` | `TEXT_PRIMARY` | `QLabel` default |
| `--text-secondary` | `TEXT_SECONDARY` | subtitles, nav idle |
| `--panel-width` | `PANEL_WIDTH` (480) | `config.MEDIUM_WIDTH` |
| `--drawer-w` | `DRAWER_WIDTH` (168) | nav drawer |
| `--radius` | `RADIUS` (16) | shell |
| `--ease-out-cubic` | `EASING_OUT_CUBIC` | `QEasingCurve.OutCubic` |

## Typography (v2 calibration)

Aligned with HTML `body` / `.view-medium`:

| Token | Value | Usage |
|-------|-------|-------|
| `FONT_FAMILY` | Segoe UI + Microsoft YaHei UI | `apply_app_font()` in [`ui/native/fonts.py`](../ui/native/fonts.py) |
| `FONT_SIZE_BASE` | 13px | Global app font, chat bubbles, inputs |
| `FONT_SIZE_TITLE` | 13px | `#TopTitle` (not 15px) |
| `FONT_SIZE_CAPTION` | 11px | `#TopSub`, status badge |
| `LINE_HEIGHT` | 1.5 | Bubble label vertical padding in QSS |

Do not override with `QFont(..., 10)` — QSS sizes depend on the 13px base.

## Content width & padding

| Rule | HTML | Native |
|------|------|--------|
| Page padding | `.content { padding: 12px 16px }` | `CONTENT_PAD_V=12`, `CONTENT_PAD_H=16` on all medium pages |
| Chat gap | 12px | `_chat_layout.setSpacing(12)` |
| Bubble max-width | 85% | `ChatBubble` + `BUBBLE_MAX_RATIO=0.85`; user bubbles right-aligned |
| Step rows | full-width `.step` | `StepItem` `Expanding` horizontal policy |

## Layout (viewMedium)

- Panel: **480 × 520** px
- Compact: **320 × 48–52** px pill (max grow **96** px), radius 26px, no drop shadow
- Drawer: 168px overlay from left + semi-transparent backdrop
- Nav: 5 items (guide, steps, blueprint, notifications, settings) with SVG icons

## Dual-mode window (native v2)

| Mode | Default size | Resize | Auto switch |
|------|--------------|--------|-------------|
| **Medium** | 480×520 (remembered) | 8-edge drag, min 360×300, max 90% screen | On `process_success` when steps exist |
| **Compact** | 320×48 pill | Auto height/width from input only | On `_finish_task` |

- Compact pill: `CompactShell[pill=true]` border-radius 26px; multi-line → `[pill=false]` 16px rect, max height 96px
- Input dock: `QFrame#InputFloat` surface card + ghost send button (`SendBtnGhost`)
- Enter: medium `ChatInput` and compact input submit; Shift+Enter newline (medium)
- Animations: [`ui/native/motion.py`](../ui/native/motion.py) — **250ms** mode switch (opacity only), **120ms** compact grow, drawer 200ms
- Status badge pulse: only `processing → executing`
- Anchor: window resizes keep **bottom-right** fixed

## Verification (native vs web)

```bash
python -m ui.web_preview   # HTML canon side-by-side reference
python main.py             # native (USE_NATIVE_UI=1)
```

Checklist: bubbles ≤85% width with user right-aligned; 13px readable Chinese; compact ~52px without heavy shadow; input float card at bottom.

## Sync script

Run `python scripts/sync_design_tokens.py` to validate `layout_tokens.py` + `visual_tokens.py` against `index.html` `:root` (read-only).

Legacy re-export: [`design_tokens.py`](../ui/native/design_tokens.py). Composed QSS mirror: [`theme.qss`](../ui/native/theme.qss) (= `themes/current/*` + `_base.qss`).
