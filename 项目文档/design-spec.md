# HAJIMI UI Design Spec

**Design canon (read-only):** [`ui/web/index.html`](../ui/web/index.html) — see also [`docs/ui-html-spec.md`](ui-html-spec.md).

**Native implementation:** [`ui/native/`](../ui/native/) + [`ui/native/design_tokens.py`](../ui/native/design_tokens.py) + [`ui/native/theme.qss`](../ui/native/theme.qss).

## Rollback

| Method | Command |
|--------|---------|
| WebEngine HTML UI | `set HAJIMI_NATIVE_UI=0` then `python main.py` |
| Browser demo | `python -m ui.web_preview` |
| Git native only | `git checkout main -- ui/native/` |
| Verify fallback | `scripts\verify_web_ui_fallback.bat` |

## Token mapping

| HTML `:root` | `design_tokens.py` | QSS / usage |
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

Run `python scripts/sync_design_tokens.py` to validate tokens against `index.html` `:root` (read-only).
