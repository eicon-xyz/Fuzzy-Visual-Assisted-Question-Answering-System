@echo off
setlocal EnableExtensions
cd /d %~dp0..\HAJIMI_UI

if exist server\.venv\Scripts\python.exe (
    set "PYTHON=server\.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo [HAJIMI] Fixed-coordinate click smoke test (HTTP /debug/click on :8011)
echo [HAJIMI] Ensure L5 Sidecar is running: scripts\start_l5_sidecar.bat
echo.

"%PYTHON%" scripts\test_click_http.py --require-sidecar --x 960 --y 540 %*

endlocal
exit /b %ERRORLEVEL%
