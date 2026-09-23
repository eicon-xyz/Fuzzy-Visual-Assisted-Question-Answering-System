# HAJIMI Desktop Auto-Op Assistant

## V2 - AI-Powered Desktop Automation

User types natural language instruction -> AI captures screen -> detects elements via remote GPU OmniParser -> generates execution plan via LLM -> performs actions (click / type / keys) to complete the task.

```
[PyQt5 UI] <-- HTTP/SSE --> [FastAPI Server] <-- HTTP --> [OmniParser :9800]
```

## Quick Start

### 1. Ensure OmniParser is running on remote GPU
```bash
curl http://127.0.0.1:9800/probe/
# Expected: {"ready": true, "device": "cuda"}
```

### 2. Configure server/.env
```env
OMNIPARSER_URL=http://127.0.0.1:9800
OMNIPARSER_TIMEOUT=30
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen3.6-35B-A3B
LLM_PROVIDER=qwen
HAJIMI_DEMO_KEY=hajimi-demo-2026
```

### 3. Start A-end
```bash
server\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

### 4. Quick test (CLI)
```bash
curl -X POST http://127.0.0.1:8010/api/demo/execute \
  -H "X-Demo-Key: hajimi-demo-2026" \
  -H "Content-Type: application/json" \
  -d '{"query":"open notepad"}'
```

### 5. Start B-end (optional)
```bash
python main.py
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/demo/health` | Health + OmniParser probe |
| POST | `/api/demo/execute` | Submit task, returns plan + task_id |
| GET | `/api/demo/stream/{task_id}` | SSE event stream |
| POST | `/api/demo/cancel` | Cancel task |

## SSE Events

`plan_ready` -> `step_start` -> `step_done` -> ... -> `task_done`
Plus: `log`, `screenshot`, `heartbeat`

## Safety (3-tier)

| Level | Examples | Behavior |
|-------|----------|----------|
| GREEN | click button, open notepad, type text | auto-execute |
| YELLOW | install software, modify settings, delete file | allow with warning |
| RED | format disk, crack password, auto pay | blocked |

## Docs

- [API Contract](docs/API-CONTRACT.md)
- [Dev Guide](docs/DEV-GUIDE.md)
- [UI Spec](docs/UI-SPEC.md)
- [Backend Checklist](docs/BACKEND-CHECKLIST.md)

## Test
```bash
python -m pytest server/tests/ -q
```
