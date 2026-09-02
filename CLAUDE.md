# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**HAJIMI** — an AI-powered desktop assistant in **L5 auto-execute mode**: the user submits a natural-language instruction, the L5 Sidecar plans steps with an LLM and executes them on the desktop via UIA bindings and Playwright DOM automation, streaming progress back over SSE.

L4 guidance mode (screenshot → OmniParser → red-box annotations), the old A-end FastAPI (:8010), and the OmniParser submodule were all removed. The only runtime backend is the L5 Sidecar (`server_A/`, :8011).

## Repository Layout

```
server_A/server/               # L5 Sidecar — FastAPI backend (default :8011)
├── main.py                    # FastAPI app, CORS, lifespan; mounts all routers
├── config.py                  # Sidecar config (DEEPSEEK_API_KEY / LLM_* read from server/.env)
├── .env                       # THE single place for model keys (created by 安装全栈.bat)
├── routes/
│   ├── demo.py                # L5 core: /execute, /stream/{task_id} (SSE), /cancel, /health, /debug/click
│   ├── admin.py               # Admin + users endpoints (stats, trends, redline, /users/*) — serves web-admin
│   └── audit.py auth.py flow.py monitor.py config_client.py  # Audit, auth, flow, monitor, C-end config pull
├── services/
│   ├── executor/              # L5 execution engine: engine.py, uia_bridge.py (UIA), clicker.py, safety.py
│   ├── browser/               # Playwright DOM automation
│   ├── planning/ llm/ intent/ # LLM step planning + intent classification
│   ├── redline_service.py     # Server-side safety filter (second layer of the redline)
│   └── database/ storage/     # SQLAlchemy ORM + in-memory task store
└── requirements.txt           # Sidecar deps (installed into server_A/server/.venv)

HAJIMI_UI/                     # B-end — PyQt5 desktop client (the only GUI)
├── main.py                    # Entry point; auto-launches L5 Sidecar unless already up
├── config.py                  # B-end runtime config (env vars → module attrs), L5-only (L5_API_URL etc.)
├── core/
│   ├── api_client.py          # L5 subset: execute_task / cancel_task / check_l5_health / get_api_status_message
│   ├── execute_worker.py      # QThread: POST /api/demo/execute + consume SSE /api/demo/stream
│   ├── l5_sidecar_launcher.py # Ensure server_A Sidecar (:8011) is running (runs scripts/start_l5_sidecar.bat)
│   ├── l5_query_normalize.py  # B-end redline normalization before submit (first layer of the redline)
│   ├── sidecar_modules.py     # Dynamically load redline rules from server_A source
│   ├── env_sync.py            # sync_l5_sidecar_env(): B-end settings → server_A/server/.env
│   ├── service_manager.py     # Windows process management; only touches :8011 now
│   ├── user_settings.py       # %LOCALAPPDATA%\HAJIMI\user_settings.json (no deployment_mode/a_end_url fields)
│   ├── auth_session.py        # User login session for sidecar auth
│   ├── backend_health_worker.py # Background Sidecar health polling → status signals
│   ├── bc_signals.py          # B↔C (voice) signal/audit helpers
│   └── defaults.py            # DEFAULT_L5_PORT=8011, DEFAULT_DEMO_KEY, voice defaults
├── ui/
│   ├── main_widget.py         # Top-level shell: page nav (guide/steps/reminders/settings), tray, resize
│   ├── app_controller.py      # Central state machine — L5 auto-execute only
│   ├── step_list.py chat_bubble.py # L5 step timeline + guide chat widgets
│   └── native/                # PyQt5 widgets: medium panel, compact bar, L5 timeline, themes
│       ├── medium_panel.py    # Main panel: input, L5 steps, settings form, service status
│       ├── compact_bar.py     # Minimal floating bar for compact mode
│       ├── l5_timeline.py l5_step_row.py # L5 execution timeline rendering
│       ├── login_dialog.py    # User login
│       ├── theme_manager.py / shell_appearance.py / window_state.py
│       └── luxury/            # Luxury (variant_luxury) theme: starfield, gold text, script fonts
├── scripts/                   # Windows .bat launchers & tooling
│   ├── start_release_fullstack.bat # Used by root 启动全栈.bat: L5 Sidecar (:8011) + B-end (2 windows)
│   ├── start_local_vision.bat # Used by root 启动本地.bat: same, L5-only
│   ├── start_l5_sidecar.bat   # Launch server_A Sidecar uvicorn on :8011
│   ├── start_ui.bat           # Launch B-end client only
│   ├── stop_all.bat           # Kill :8011 by port
│   ├── verify_all.py (verify_all.bat) # Acceptance checks (--require-l5)
│   ├── apply_l5_settings.py   # Write OMNIPARSER_ENABLED=false / ROUTING_MODE=l5 into server_A/server/.env
│   ├── ensure_l5_sidecar_env.bat ensure_ui_env.bat  # venv bootstrap used by 安装全栈.bat
│   └── dev/check_bat_parens.py # Static check: unescaped ( ) inside if/for blocks in .bat
└── requirements.txt           # B-end deps: PyQt5 only

client/                        # C-end voice module (ASR/TTS, vosk/pyttsx3); server_url defaults to :8011
web-admin/                     # Vue 3 + Vite admin dashboard (Element Plus, ECharts, Pinia)
                               # → Sidecar :8011 admin/audit/auth/flow/monitor/users routes
launchers/                     # Thin root-level .bat wrappers
根目录 .bat                    # 安装全栈.bat / 启动全栈.bat / 启动本地.bat / 验收.bat / stop_all.bat / 打包.bat
```

## Key Architecture Concepts

### B-end + L5 Sidecar architecture
```
C-end voice (client/) ──┐
                        ├──HTTP + SSE──▶  L5 Sidecar (server_A FastAPI :8011)  ──▶  UIA binding / Playwright DOM
B-end (PyQt5) ──────────┘
```
- **Sidecar** exposes `/api/demo/health`; B-end polls it on startup and auto-launches the Sidecar if it's down.
- **web-admin** and C-end config-pull also talk to the same :8011 process.
- There is no deployment-mode switch and no other backend port.

### L5 submission flow
1. User types an instruction on the guide (chat) page → L5 informed-consent confirmation.
2. `l5_query_normalize.normalize_l5_execute_query()` applies B-end redline rules (loaded from server_A via `sidecar_modules`); unsafe queries never leave the B-end.
3. `ExecuteWorkerThread` POSTs `/api/demo/execute` (header `X-Demo-Key`); the Sidecar re-checks redlines server-side (two-layer safety).
4. The Sidecar plans steps with the LLM, then executes via UIA bindings and Playwright DOM.
5. Progress streams back over SSE `/api/demo/stream/{task_id}`: `step_start / step_done / step_blocked / step_failed / task_done` … events render into the steps timeline.
6. Desktop hotkeys: `H` approve, `P` pause, `J` stop.

### Auto-Launch Flow
B-end `main.py` spawns a daemon thread at startup that calls the L5 sidecar launcher; if the Sidecar health check fails, it starts `scripts\start_l5_sidecar.bat` in a new console window and polls health with configurable delay/retry. `ExecuteWorkerThread` re-checks health before submitting.

### Environment Variables (B-end)
| Variable | Purpose | Default |
|----------|---------|---------|
| `L5_API_URL` | Full Sidecar URL | `http://127.0.0.1:8011` |
| `L5_API_HOST` / `L5_API_PORT` | Sidecar host/port (used if `L5_API_URL` unset) | `127.0.0.1` / `8011` |
| `HAJIMI_L5_ROOT` | server_A root override | repo-relative `../server_A` |
| `HAJIMI_AUTO_LAUNCH_L5` | Auto-start Sidecar on B-end launch | `1` |
| `HAJIMI_STOP_SERVICES_ON_EXIT` | Kill Sidecar (:8011) on B-end close | `1` |
| `HAJIMI_DEMO_KEY` | `X-Demo-Key` value | `hajimi-demo-2026` |
| `HAJIMI_EXECUTE_TIMEOUT` | Execute/SSE timeout in seconds | `360` |

### Model Keys & Settings Persistence
- Model keys live **only** in `server_A/server/.env` (`DEEPSEEK_API_KEY`, `LLM_*`). `OMNIPARSER_ENABLED=false` and `ROUTING_MODE=l5` are written into that file by `scripts/apply_l5_settings.py`.
- B-end settings persist at `%LOCALAPPDATA%\HAJIMI\user_settings.json` (no `deployment_mode` / `a_end_url` / omniparser / l4 fields). `apply_user_settings()` writes values to `os.environ` then calls `config.reload_from_env()` and `api_client.reload_client_config()`. Saving the settings page calls `env_sync.sync_l5_sidecar_env()` to merge keys into `server_A/server/.env`, then restarts the Sidecar.

## Common Commands

```bash
# Root — first-time install: creates 2 venvs (HAJIMI_UI/.venv + server_A/server/.venv)
安装全栈.bat

# Root — start everything: L5 Sidecar (:8011) + B-end, two windows
# (delegates to HAJIMI_UI/scripts/start_release_fullstack.bat)
启动全栈.bat

# Root — local dev start (delegates to HAJIMI_UI/scripts/start_local_vision.bat, also L5-only)
启动本地.bat

# Root — stop (kills :8011 only)
stop_all.bat

# Root — acceptance check (HAJIMI_UI/scripts/verify_all.py --require-l5)
验收.bat

# B-end alone (Sidecar must already be running, else B-end auto-launches it)
cd HAJIMI_UI
python main.py

# L5 Sidecar alone
HAJIMI_UI\scripts\start_l5_sidecar.bat
```

## Important Constraints

- **Windows-only**: `.bat` scripts, PyQt5 frameless windows, `taskkill`, and UIA execution are Windows-specific. Linux/macOS can only run `python main.py` with limitations.
- **Single backend**: the only supported runtime backend is `server_A` L5 Sidecar at `127.0.0.1:8011`. No :8010, no OmniParser, no campus GPU tunnel, no Mock backend — do not reintroduce them.
- **Two venvs**: `HAJIMI_UI/.venv` (B-end; deps = `PyQt5` only, per `HAJIMI_UI/requirements.txt`) and `server_A/server/.venv` (Sidecar). `安装全栈.bat` creates both.
- **Model keys**: stored only in `server_A/server/.env` (`DEEPSEEK_API_KEY` / `LLM_*`); B-end settings sync there via `core/env_sync.py` and restart the Sidecar.
- **Demo/auth**: all `/api/demo/*` endpoints except `/health` require the `X-Demo-Key: hajimi-demo-2026` header.
- **Redline is two-layered**: B-end `l5_query_normalize` first, Sidecar `redline_service`/`executor/safety` second; both must stay in sync (B-end loads rules from server_A source).
- **Task storage is in-memory**: tasks/steps/state are lost on Sidecar restart (demo phase).
- **.bat files**: must be GBK-encoded or pure ASCII, CRLF endings; never `echo` unescaped `( )` inside `if`/`for` parenthesized blocks (`HAJIMI_UI/scripts/dev/check_bat_parens.py` checks this).
