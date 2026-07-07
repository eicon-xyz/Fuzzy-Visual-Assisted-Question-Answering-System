@echo off
setlocal EnableExtensions
cd /d %~dp0..

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
set HAJIMI_API_URL=http://127.0.0.1:%HAJIMI_PORT%

echo [HAJIMI] L4-only mode - A-end + LLM only, no OmniParser tunnel required
echo [HAJIMI] Ensure server\.env has LLM_API_KEY + ROUTING_MODE=auto or fast

if not exist server\.env (
    echo [HAJIMI] Missing server\.env - copy from server\.env.example
    exit /b 1
)

echo [HAJIMI] Starting A-end on :%HAJIMI_PORT% ...
start "HAJIMI-A-end-L4" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& call %~dp0start_server.bat"

echo [HAJIMI] Waiting for A-end /health/live ...
set /a WAIT=0
:wait_live
set /a WAIT+=1
if %WAIT% GTR 45 (
    echo [HAJIMI] TIMEOUT: A-end not ready. Check HAJIMI-A-end-L4 window.
    exit /b 1
)
"%PYTHON%" -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:%HAJIMI_PORT%/api/demo/health/live',timeout=3); d=json.loads(r.read()); exit(0 if d.get('status')=='ok' else 1)" 2>nul
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_live
)
echo [HAJIMI] A-end live - L4 tasks need LLM only (inspect/precision still need OmniParser)

echo [HAJIMI] Starting B-end UI ...
start "HAJIMI-B-end" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& set HAJIMI_API_URL=%HAJIMI_API_URL%&& call %~dp0start_ui.bat"

echo [HAJIMI] Done. Use Settings - fast mode for L4 Vision path.
endlocal
exit /b 0
