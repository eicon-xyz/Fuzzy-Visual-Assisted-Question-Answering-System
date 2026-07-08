@echo off
setlocal EnableExtensions
cd /d %~dp0..\HAJIMI_UI

call scripts\ensure_l5_sidecar_env.bat
if errorlevel 1 (
    endlocal
    exit /b 1
)

if defined HAJIMI_L5_ROOT (
    set "L5_ROOT=%HAJIMI_L5_ROOT%"
) else (
    set "L5_ROOT=%~dp0..\new_JIMI\HAJIMI_UI"
)

set "L5_PY=%L5_ROOT%\server\.venv\Scripts\python.exe"
if not exist "%L5_PY%" (
    echo [HAJIMI] ERROR: L5 venv python not found: %L5_PY%
    endlocal
    exit /b 1
)

echo [HAJIMI] Fixed-coordinate click smoke test (direct clicker)
"%L5_PY%" scripts\test_click_fixed.py --x 960 --y 540 --delay 3 %*

endlocal
exit /b %ERRORLEVEL%
