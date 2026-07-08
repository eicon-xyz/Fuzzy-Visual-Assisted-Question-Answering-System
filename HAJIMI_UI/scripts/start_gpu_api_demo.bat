@echo off
setlocal EnableExtensions
cd /d %~dp0..

if /I not "%HAJIMI_DEGRADED_START%"=="0" (
    set "HAJIMI_DEGRADED_START=1"
) else (
    set "HAJIMI_DEGRADED_START=0"
)

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

call "%~dp0ensure_server_env.bat"
if errorlevel 1 exit /b 1
call "%~dp0ensure_l5_sidecar_env.bat"
if errorlevel 1 exit /b 1

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
)

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
set HAJIMI_API_URL=http://127.0.0.1:%HAJIMI_PORT%
set NO_PROXY=127.0.0.1,localhost
set no_proxy=127.0.0.1,localhost

echo [HAJIMI] GPU API mode — OmniParser via tunnel :9800
"%PYTHON%" scripts\check_gpu_api_tunnel.py
if errorlevel 1 (
    if "%HAJIMI_DEGRADED_START%"=="1" (
        echo [HAJIMI] WARN: :9800 tunnel not ready — UI will start in not-connected state
    ) else (
        echo [HAJIMI] Open tunnel first: scripts\start_tunnel_9800.bat
        exit /b 1
    )
)

"%PYTHON%" scripts\setup_gpu_api_mode.py
if errorlevel 1 exit /b 1

echo [HAJIMI] Starting local A-end on :%HAJIMI_PORT% (OmniParser via tunnel :9800) ...
start "HAJIMI-A-end-GPU-API" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& call %~dp0start_server.bat"
timeout /t 2 /nobreak >nul
start "HAJIMI-L5-Sidecar" cmd /k "set L5_API_PORT=8011&& call %~dp0start_l5_sidecar.bat"

echo [HAJIMI] Waiting for A-end health ...
set /a WAIT=0
:wait_health
set /a WAIT+=1
if %WAIT% GTR 45 (
    if "%HAJIMI_DEGRADED_START%"=="1" (
        echo [HAJIMI] WARN: A-end not ready in 90s — continuing to UI ^(will retry in app^)
        goto start_ui
    )
    echo [HAJIMI] TIMEOUT: A-end not ready. Check HAJIMI-A-end-GPU-API window.
    exit /b 1
)
"%PYTHON%" -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:%HAJIMI_PORT%/api/demo/health',timeout=3); d=json.loads(r.read()); exit(0 if d.get('status')=='ok' and d.get('omniparser_ready') else 1)" 2>nul
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_health
)
echo [HAJIMI] A-end ready — omniparser via GPU tunnel

if not defined L5_API_PORT set L5_API_PORT=8011
echo [HAJIMI] Waiting for L5 Sidecar :%L5_API_PORT% ...
set /a WAIT_L5=0
:wait_l5
set /a WAIT_L5+=1
if %WAIT_L5% GTR 45 (
    echo [HAJIMI] WARN: L5 Sidecar not ready — continuing with L3/L4 only.
    echo [HAJIMI] Check HAJIMI-L5-Sidecar window; ensure new_JIMI\HAJIMI_UI\server\.venv and .env exist.
    goto start_ui
)
"%PYTHON%" scripts\check_l5_sidecar_live.py --port %L5_API_PORT% 2>nul
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_l5
)
echo [HAJIMI] L5 Sidecar ready on :%L5_API_PORT%

:start_ui
echo [HAJIMI] Starting B-end UI ...
if not defined VIDEO_RAG_PY if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "VIDEO_RAG_PY=%~dp0..\.venv\Scripts\python.exe"
)
start "HAJIMI-B-end" cmd /k "set PYTHON=&& set HAJIMI_PORT=%HAJIMI_PORT%&& set HAJIMI_API_URL=%HAJIMI_API_URL%&& if defined VIDEO_RAG_PY set VIDEO_RAG_PY=%VIDEO_RAG_PY%&& call %~dp0start_client.bat"

echo [HAJIMI] Launched. UI uses local mode + OMNIPARSER_URL=http://127.0.0.1:9800
endlocal
exit /b 0
