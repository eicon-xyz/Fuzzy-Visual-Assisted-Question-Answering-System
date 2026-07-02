# UI HTML Spec (design canon)

**Source (read-only):** [`ui/web/index.html`](../ui/web/index.html)

PyQt native UI must match **`body.desktop-host`** rules, not the floating browser demo positions.

## Views

| HTML | Native | desktop-host |
|------|--------|--------------|
| `#viewMedium` | `MediumPanel` / `#NativeShell` | Fill host window, radius 16px |
| `#viewCompact` | `CompactBar` / `#CompactShell` | Height **52px**, width 100%, radius 16px |

## Compact DOM (`#viewCompact`)

```
.view-compact
├── .compact-mark     "✦"  32×32 accent-soft box
├── .compact-input    single line, placeholder "Ask HAJIMI…"
└── .compact-hint     "↵"
```

- Padding: `6px 8px 6px 10px`, gap 12px
- Click shell (not input) → medium
- Enter + text → submit + medium

## Medium DOM (`#viewMedium`)

```
.shell
├── .nav-backdrop
├── .nav-drawer (168px overlay)
└── .main
    ├── .medium-top-switch   ◀ only (desktop-host hides ▶)
    ├── .medium-resize-handle
    ├── .topbar              menu-btn + title/sub + mode-pills
    ├── .content             padding 12px 16px 14px
    │   └── .page × 5
    ├── .thinking-strip
    ├── .medium-step-controls
    └── .input-dock > .input-float > textarea + .input-actions
```

## Tokens (`:root`)

See [`ui/native/design_tokens.py`](../ui/native/design_tokens.py). Validate with `python scripts/sync_design_tokens.py`.

## B-end extensions (html_plus)

Not in HTML medium settings. Native adds **Card 2「开发者」** below the 5 `.set` toggles on Settings page.

## Verification

```bash
python -m ui.web_preview
python main.py
python scripts/sync_design_tokens.py
```
