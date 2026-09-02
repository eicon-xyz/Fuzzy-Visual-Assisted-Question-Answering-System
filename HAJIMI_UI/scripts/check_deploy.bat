@echo off
setlocal EnableExtensions
cd /d %~dp0..

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo [HAJIMI] Ensuring venv deps (install if missing) ...
call "%~dp0ensure_ui_env.bat"
call "%~dp0ensure_server_env.bat"
call "%~dp0ensure_l5_sidecar_env.bat"

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
)

echo.
"%PYTHON%" scripts\check_deploy.py
set ERR=%ERRORLEVEL%
echo.
if "%ERR%"=="0" (
    echo [HAJIMI] Deploy check: all OK.
) else if "%ERR%"=="2" (
    echo [HAJIMI] Deploy check: env OK, backend links not ready.
) else (
    echo [HAJIMI] Deploy check: environment issues - see above.
)
pause
endlocal
exit /b %ERR%
