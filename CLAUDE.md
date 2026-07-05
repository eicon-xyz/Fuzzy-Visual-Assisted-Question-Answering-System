# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**HAJIMI** — an AI-powered desktop assistant that analyzes screen content via OmniParser vision model, plans multi-step operation guides with LLM reasoning, and overlays visual annotations on-screen.

Two deployment modes: **local** (OmniParser + A-end on same machine) and **intranet** (remote campus GPU A-end accessed via VPN/SSH tunnel).

## Repository Layout

```
HAJIMI_UI/                     # Main project (B-end + A-end + OmniParser)
├── main.py                    # B-end entry point — PyQt5 desktop client
├── config.py                  # B-end runtime config (env vars → module attrs)
├── core/                      # B-end backend (no UI)
│   ├── api_client.py          # HTTP client → A-end REST API
│   ├── a_end_launcher.py      # Auto-start A-end process on B-end startup
│   ├── app_controller.py      # Central state machine: steps, inspect, overlay
│   ├── task_worker.py         # QThread: screenshot → API process → steps
│   ├── inspect_worker.py      # QThread: screenshot → API inspect → UI elements
│   ├── relocate_worker.py     # QThread: re-screenshot → API relocate
│   ├── service_manager.py     # Windows process management (kill/start A-end & OmniParser)
│   ├── user_settings.py       # Persist settings to %LOCALAPPDATA%\HAJIMI\user_settings.json
│   ├── screen_utils.py        # Screenshot capture (mss → PIL), redline check, fingerprint
│   ├── mock_backend.py        # "安装微信" demo flow (3 steps with hardcoded bbox annotations)
│   ├── env_sync.py            # Sync B-end settings → server/.env
│   ├── coordinate_mapper.py   # Map OmniParser coordinates to screen overlay positions
│   ├── overlay_coords.py      # DPR-aware: capture physical pixels → Qt logical coords
│   ├── annotation_mapper.py   # Convert server annotation dicts to overlay draw items
│   ├── deployment_resolver.py # Probe local ports for campus GPU health on startup
│   └── defaults.py            # Shared constants: DEFAULT_A_PORT=8010, DEFAULT_OMNI_LOCAL_URL=:8002
├── ui/
│   ├── main_widget.py         # Top-level shell: mode switching (medium/compact), tray, resize
│   ├── app_controller.py      # (symlink) → core/app_controller.py
│   ├── native/                # PyQt5 widgets: medium panel, compact bar, overlays
│   │   ├── medium_panel.py    # Main panel: input, steps list, settings form, service controls
│   │   ├── compact_bar.py     # Minimal floating bar for compact mode
│   │   ├── overlay_anno.py    # Transparent overlay window for screen annotations
│   │   ├── suspension_dialog.py / prepare_step_dialog.py  # Modal dialogs
│   │   ├── theme_manager.py   # Runtime theme switching (variant_c/variant_luxury)
│   │   ├── shell_appearance.py # Per-theme QSS generation, glass/solid/crystal modes
│   │   ├── window_state.py    # Save/restore window position, size, mode
│   │   └── luxury/            # Luxury (variant_luxury) theme: starfield, gold text, script fonts
│   ├── overlay_anno.py        # (symlink)
│   └── web/                   # Legacy WebEngine UI (seldom used; native is default)
├── scripts/                   # Windows .bat launchers
│   ├── start_all.bat          # One-click: kill ports → OmniParser → A-end → B-end
│   ├── start_omniparser.bat   # Launch OmniParser server (CPU mode by default)
│   ├── start_server.bat       # Launch A-end uvicorn
│   ├── start_ui.bat           # Launch B-end client
│   ├── stop_all.bat           # Kill OmniParser + A-end by port
│   ├── setup.bat              # First-time init: venv, requirements, weight check
│   └── setup_server_env.bat   # Create server venv and install server/requirements.txt
├── server/                    # A-end — FastAPI backend
│   ├── main.py                # FastAPI app, CORS, lifespan, exception handlers
│   ├── config.py              # Server config: LLM_* / DEEPSEEK_* priority, OmniParser settings
│   ├── routes/demo.py         # 7 demo endpoints: health, process, inspect, step, relocate, clarify, report
│   ├── routes/admin.py        # 9 admin endpoints: stats, trends, redline, feedback, config
│   ├── services/              # Core backend logic
│   │   ├── llm_ai.py          # Compatibility router → llm/ or legacy
│   │   ├── omniparser_client.py  # HTTP client for OmniParser V2 (local :8002 or GPU :9800)
│   │   ├── redline_service.py # Safety filter: reject physical-operation / privacy-intrusion queries
│   │   ├── llm/client.py      # Multi-model LLM client (OpenAI-compatible, supports vision)
│   │   ├── llm/prompt.py      # System prompt with SoM rules + WPS few-shot examples
│   │   ├── planning/          # Step generation, re-planning, blueprint state machine
│   │   ├── perception/        # UI element serialization → LLM prompt
│   │   └── intent/            # SetFit intent classifier + keywords fallback
│   ├── database/models.py     # SQLAlchemy ORM (7 tables: tasks, steps, audits, etc.)
│   ├── storage/memory.py      # In-memory task store (demo phase)
│   └── tests/                 # pytest suite (conftest.py + test_*.py)
├── OmniParser/                # Microsoft OmniParser V2 (submodule)
│   └── omnitool/omniparserserver/  # HTTP server wrapping YOLO icon-detect + Florence caption
└── web-admin/                 # Vue 3 + Vite admin dashboard (Element Plus, ECharts, Pinia)
    └── src/                   # Connects to A-end /api/admin/*
```

## Key Architecture Concepts

### Three-Process Architecture
```
B-end (PyQt5 client)  ──HTTP──▶  A-end (FastAPI :8010)  ──HTTP──▶  OmniParser (:8002 or :9800)
```
- **OmniParser** must start first (YOLO icon-detect loads ~2 min on CPU)
- **A-end** health endpoint reports `detector_backend` and `omniparser_ready`
- **B-end** polls `/api/demo/health` on startup; auto-launches A-end if local mode

### B-end Processing Pipeline
1. User submits query → `TaskWorkerThread.run()`
2. Thread captures full screen via `mss` → PIL Image
3. Checks redline keywords locally; aborts if triggered
4. POSTs screenshot as base64 data-URI to `/api/demo/process`
5. A-end sends screenshot → OmniParser for UI element detection + SoM annotation
6. LLM (Qwen3.6 via SiliconCloud) receives annotated image + element list; plans steps
7. Response contains `steps[]` with `annotation` containing bounding boxes
8. `AppController` maps coordinates, emits overlay signals
9. `OverlayAnnoWindow` renders highlight boxes and arrows on transparent overlay

### Coordinate Pipeline
Screenshots (physical pixels via mss) → OmniParser (resized to max 1920px) → LLM step generation → `coordinate_mapper` adjusts for DPR + screen metrics → overlay annotations drawn in logical pixels on transparent window.

### Auto-Launch Flow
B-end `main.py` spawns a daemon thread at startup that calls `ensure_a_end_running()`. If A-end health check fails in local mode, it starts `scripts\start_server.bat` in a new console window and polls health with configurable delay/retry (up to ~75s). Worker threads also call `ensure_a_end_running()` as a safety net before capturing screenshots.

### Environment Variables (B-end)
| Variable | Purpose | Default |
|----------|---------|---------|
| `HAJIMI_PORT` | A-end port | `8010` |
| `HAJIMI_HOST` | A-end host | `127.0.0.1` |
| `HAJIMI_API_URL` | Full A-end URL (overrides host/port) | `http://127.0.0.1:8010` |
| `HAJIMI_DEPLOYMENT_MODE` | `local` or `intranet` | `local` |
| `HAJIMI_MOCK_ONLY` | Skip A-end entirely, use `mock_backend.py` | `0` |
| `HAJIMI_MOCK_FALLBACK` | Fall back to mock if A-end unreachable | `0` |
| `HAJIMI_AUTO_LAUNCH_A_END` | Auto-start A-end on B-end launch | `1` |
| `HAJIMI_STOP_SERVICES_ON_EXIT` | Kill A-end + OmniParser on B-end close | `1` |

### User Settings Persistence
Settings stored at `%LOCALAPPDATA%\HAJIMI\user_settings.json`. `apply_user_settings()` writes values to `os.environ` then calls `config.reload_from_env()` and `api_client.reload_client_config()`. When user saves settings in the settings panel, `env_sync.sync_server_env()` also merges relevant values into `server/.env`.

## Common Commands

```bash
# B-end — Mock mode (no backend needed)
cd HAJIMI_UI
set HAJIMI_MOCK_ONLY=1
python main.py

# B-end — Connect to A-end (A-end must already be running)
python main.py

# A-end — Start server
cd HAJIMI_UI
python -m uvicorn server.main:app --host 127.0.0.1 --port 8010

# Full local stack (Windows .bat)
scripts\start_all.bat

# Run A-end tests
cd HAJIMI_UI
pytest server/tests/ -v

# Web admin dashboard
cd web-admin
npm run dev          # Dev server on :5173
npm run build        # Production build → dist/

# UI style preview (no backend)
python -m ui.style_preview_demo
```

## Important Constraints

- **Windows-only**: `.bat` scripts, `mss` screenshots, PyQt5 frameless windows, and `taskkill` are Windows-specific. Linux/macOS can only run `python main.py` with limitations.
- **OmniParser is heavy**: CPU mode takes 2–4 minutes per frame. The Florence caption model + YOLO icon-detect model require ~4GB RAM. Timeouts are set to 360s.
- **Python environments**: B-end uses system Python (`C:\ProgramData\anaconda3\python.exe`). OmniParser uses a separate conda env (`omni`) due to PyTorch version conflicts. The `.bat` scripts reference these explicitly.
- **Server config priority**: `LLM_API_KEY` > `DEEPSEEK_API_KEY`. If LLM_* vars are set, they're used exclusively (no fallback to DeepSeek).
- **Demo/auth**: All `/api/demo/*` endpoints except `/health` require `X-Demo-Key: hajimi-demo-2026` header.
- **Task storage is in-memory**: Tasks, steps, and state are lost on A-end restart (demo phase).
