@echo off
setlocal EnableExtensions
cd /d %~dp0..

echo [HAJIMI] Ensuring venv deps (install if missing) ...
call "%~dp0ensure_ui_env.bat"
call "%~dp0ensure_l5_sidecar_env.bat"

call "%~dp0_resolve_l5_root.bat"
set "PYTHON=python"
if exist "%L5_ROOT%\server\.venv\Scripts\python.exe" set "PYTHON=%L5_ROOT%\server\.venv\Scripts\python.exe"

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
