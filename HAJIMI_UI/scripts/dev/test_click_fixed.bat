@echo off
setlocal EnableExtensions
cd /d %~dp0\..

call ensure_l5_sidecar_env.bat
if errorlevel 1 (
    endlocal
    exit /b 1
)

call _resolve_l5_root.bat

set "L5_PY=%L5_ROOT%\server\.venv\Scripts\python.exe"
if not exist "%L5_PY%" (
    echo [HAJIMI] ERROR: L5 venv python not found: %L5_PY%
    endlocal
    exit /b 1
)

echo [HAJIMI] Fixed-coordinate click smoke test (direct clicker)
cd /d %~dp0..\..
"%L5_PY%" scripts\test_click_fixed.py --x 960 --y 540 --delay 3 %*

endlocal
exit /b %ERRORLEVEL%
