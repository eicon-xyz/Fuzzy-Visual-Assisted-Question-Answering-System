@echo off
setlocal EnableExtensions
cd /d %~dp0..

echo ============================================================
echo  HAJIMI release fullstack: L5 Sidecar :8011 + B UI
echo  L5 auto-execute mode - no L4 guide, no :8010, no OmniParser
echo ============================================================

if not exist "..\server_A\scripts\start_server.bat" (
    echo [HAJIMI] ERROR: server_A not found next to HAJIMI_UI.
    echo   Expected: repo\server_A\  and  repo\HAJIMI_UI\
    endlocal
    exit /b 1
)

call "%~dp0ensure_ui_env.bat"
if errorlevel 1 goto fail
call "%~dp0ensure_l5_sidecar_env.bat"
if errorlevel 1 goto fail

call "%~dp0_resolve_l5_root.bat"
set "PYTHON=python"
if exist "%L5_ROOT%\server\.venv\Scripts\python.exe" set "PYTHON=%L5_ROOT%\server\.venv\Scripts\python.exe"

echo.
echo [HAJIMI] Bootstrapping env - create Sidecar .env from example if missing ...
"%PYTHON%" scripts\bootstrap_release_env.py
if errorlevel 1 goto fail

echo [HAJIMI] Writing L5 mode settings - auto-execute only ...
"%PYTHON%" scripts\apply_l5_settings.py
if errorlevel 1 goto fail

if not defined L5_API_PORT set L5_API_PORT=8011
set L5_API_URL=http://127.0.0.1:%L5_API_PORT%
set NO_PROXY=127.0.0.1,localhost
set no_proxy=127.0.0.1,localhost

echo.
echo [HAJIMI] Starting L5 Sidecar on :%L5_API_PORT% ...
start "HAJIMI-L5-Sidecar" cmd /k "set L5_API_PORT=%L5_API_PORT%&& call %~dp0start_l5_sidecar.bat"
ping -n 3 127.0.0.1 >nul 2>&1

echo [HAJIMI] Waiting for L5 Sidecar :%L5_API_PORT% ...
set /a WAIT_L5=0
:wait_l5
set /a WAIT_L5+=1
if %WAIT_L5% GTR 45 (
    echo [HAJIMI] ERROR: L5 Sidecar not ready - auto-execute will fail.
    echo [HAJIMI] Check HAJIMI-L5-Sidecar window; try: cd ..\server_A ^&^& scripts\repair_l5_venv.bat
    goto fail
)
"%PYTHON%" scripts\check_l5_sidecar_live.py --port %L5_API_PORT% 2>nul
if errorlevel 1 (
    ping -n 3 127.0.0.1 >nul 2>&1
    goto wait_l5
)
echo [HAJIMI] L5 Sidecar live on :%L5_API_PORT%

echo [HAJIMI] Starting B-end UI ...
if not defined VIDEO_RAG_PY if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "VIDEO_RAG_PY=%~dp0..\.venv\Scripts\python.exe"
)
start "HAJIMI-B-end" cmd /k "set PYTHON=&& set L5_API_URL=%L5_API_URL%&& if defined VIDEO_RAG_PY set VIDEO_RAG_PY=%VIDEO_RAG_PY%&& call %~dp0start_client.bat"

echo.
echo [HAJIMI] Full stack launched - L5 auto-execute mode.
echo   Exec:    UIA binding + Playwright DOM via Sidecar :8011
echo   Verify:  scripts\verify_all.bat --require-l5
endlocal
exit /b 0

:fail
echo [HAJIMI] Startup failed - see messages above.
pause
endlocal
exit /b 1
