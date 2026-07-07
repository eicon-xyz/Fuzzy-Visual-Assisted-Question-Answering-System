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

echo [HAJIMI] GPU API mode — requires scripts\start_tunnel_9800.bat in another window
"%PYTHON%" scripts\check_gpu_api_tunnel.py
if errorlevel 1 (
    echo [HAJIMI] Open tunnel first: scripts\start_tunnel_9800.bat
    exit /b 1
)

"%PYTHON%" scripts\setup_gpu_api_mode.py
if errorlevel 1 exit /b 1

if not exist server\.venv\Scripts\python.exe (
    echo [HAJIMI] Missing server\.venv — run scripts\setup_server_env.bat
    exit /b 1
)

echo [HAJIMI] Starting local A-end on :%HAJIMI_PORT% (OmniParser via tunnel :9800) ...
start "HAJIMI-A-end-GPU-API" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& call %~dp0start_server.bat"

echo [HAJIMI] Waiting for A-end health ...
set /a WAIT=0
:wait_health
set /a WAIT+=1
if %WAIT% GTR 45 (
    echo [HAJIMI] TIMEOUT: A-end not ready. Check HAJIMI-A-end-GPU-API window.
    exit /b 1
)
"%PYTHON%" -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:%HAJIMI_PORT%/api/demo/health',timeout=3); d=json.loads(r.read()); exit(0 if d.get('status')=='ok' and d.get('omniparser_ready') else 1)" 2>nul
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_health
)
echo [HAJIMI] A-end ready — omniparser via GPU tunnel

echo [HAJIMI] Starting B-end UI ...
start "HAJIMI-B-end" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& set HAJIMI_API_URL=%HAJIMI_API_URL%&& call %~dp0start_ui.bat"

echo [HAJIMI] Launched. UI uses local mode + OMNIPARSER_URL=http://127.0.0.1:9800
endlocal
exit /b 0
