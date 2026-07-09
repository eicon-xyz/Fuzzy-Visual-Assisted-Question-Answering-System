@echo off
setlocal EnableExtensions
cd /d %~dp0..

echo ============================================================
echo  HAJIMI release fullstack: A-end :8010 + L5 :8011 + B UI
echo  L4 Vision + L5 auto-execute (no MOCK)
echo ============================================================

if not exist "..\server_A\scripts\start_server.bat" (
    echo [HAJIMI] ERROR: server_A not found next to HAJIMI_UI.
    echo   Expected: repo\server_A\  and  repo\HAJIMI_UI\
    endlocal
    exit /b 1
)

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

call "%~dp0ensure_ui_env.bat"
if errorlevel 1 goto fail
call "%~dp0ensure_server_env.bat"
if errorlevel 1 goto fail
call "%~dp0ensure_l5_sidecar_env.bat"
if errorlevel 1 goto fail

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
)

"%PYTHON%" scripts\bootstrap_release_env.py
if errorlevel 1 goto fail

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
if not defined L5_API_PORT set L5_API_PORT=8011
set HAJIMI_API_URL=http://127.0.0.1:%HAJIMI_PORT%
set NO_PROXY=127.0.0.1,localhost
set no_proxy=127.0.0.1,localhost

echo.
echo [HAJIMI] Probing OmniParser GPU tunnel :9800 ...
"%PYTHON%" scripts\check_gpu_api_tunnel.py >nul 2>&1
if errorlevel 1 (
    echo [HAJIMI] WARN: :9800 not ready — L4 Vision still works; precision/inspect need OmniParser.
    echo [HAJIMI]       To enable GPU API: scripts\start_tunnel_9800.bat or 启动本地.bat
) else (
    echo [HAJIMI] Tunnel OK — applying gpu_api settings
    "%PYTHON%" scripts\setup_gpu_api_mode.py
    if errorlevel 1 goto fail
)

echo.
echo [HAJIMI] Starting A-end on :%HAJIMI_PORT% ...
start "HAJIMI-A-end" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& call %~dp0start_server.bat"
timeout /t 2 /nobreak >nul

echo [HAJIMI] Starting L5 Sidecar on :%L5_API_PORT% ...
start "HAJIMI-L5-Sidecar" cmd /k "set L5_API_PORT=%L5_API_PORT%&& call %~dp0start_l5_sidecar.bat"
timeout /t 2 /nobreak >nul

echo [HAJIMI] Waiting for A-end /health/live ...
set /a WAIT=0
:wait_a
set /a WAIT+=1
if %WAIT% GTR 45 (
    echo [HAJIMI] TIMEOUT: A-end not ready. Check HAJIMI-A-end window.
    goto fail
)
"%PYTHON%" -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:%HAJIMI_PORT%/api/demo/health/live',timeout=3); d=json.loads(r.read()); exit(0 if d.get('status')=='ok' else 1)" 2>nul
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_a
)
echo [HAJIMI] A-end live on :%HAJIMI_PORT%

echo [HAJIMI] Waiting for L5 Sidecar :%L5_API_PORT% ...
set /a WAIT_L5=0
:wait_l5
set /a WAIT_L5+=1
if %WAIT_L5% GTR 45 (
    echo [HAJIMI] ERROR: L5 Sidecar not ready — L5 auto-execute will fail.
    echo [HAJIMI] Check HAJIMI-L5-Sidecar window; try: cd server_A ^&^& scripts\repair_l5_venv.bat
    goto fail
)
"%PYTHON%" scripts\check_l5_sidecar_live.py --port %L5_API_PORT% 2>nul
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_l5
)
echo [HAJIMI] L5 Sidecar live on :%L5_API_PORT%

echo [HAJIMI] Starting B-end UI ...
if not defined VIDEO_RAG_PY if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "VIDEO_RAG_PY=%~dp0..\.venv\Scripts\python.exe"
)
start "HAJIMI-B-end" cmd /k "set PYTHON=&& set HAJIMI_PORT=%HAJIMI_PORT%&& set HAJIMI_API_URL=%HAJIMI_API_URL%&& if defined VIDEO_RAG_PY set VIDEO_RAG_PY=%VIDEO_RAG_PY%&& call %~dp0start_client.bat"

echo.
echo [HAJIMI] Full stack launched.
echo   L4: Settings - routing fast/balanced/auto
echo   L5: Settings - routing l5 + enable auto-execute
echo   Verify: scripts\verify_all.bat --require-a
endlocal
exit /b 0

:fail
echo [HAJIMI] Startup failed — see messages above.
pause
endlocal
exit /b 1
