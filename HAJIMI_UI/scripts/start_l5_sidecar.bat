@echo off
setlocal EnableExtensions

cd /d %~dp0..

if not defined L5_API_PORT set L5_API_PORT=8011
set HAJIMI_PORT=%L5_API_PORT%
if not defined HAJIMI_HOST set HAJIMI_HOST=127.0.0.1

if exist "%~dp0..\server\.venv\Scripts\python.exe" (
    set "KILL_PY=%~dp0..\server\.venv\Scripts\python.exe"
) else (
    set "KILL_PY=python"
)
echo [HAJIMI] Freeing port %L5_API_PORT% (stale L5 Sidecar) ...
"%KILL_PY%" "%~dp0kill_port.py" %L5_API_PORT% >nul 2>&1

call "%~dp0_resolve_l5_root.bat"

if not exist "%L5_ROOT%\scripts\start_server.bat" (
    echo [HAJIMI] ERROR: L5 Sidecar not found at:
    echo   %L5_ROOT%
    echo Set HAJIMI_L5_ROOT to server_A if using a custom path.
    endlocal
    exit /b 1
)

call "%~dp0ensure_l5_sidecar_env.bat"
if errorlevel 1 (
    endlocal
    exit /b 1
)

echo [HAJIMI] Starting L5 Sidecar on http://%HAJIMI_HOST%:%HAJIMI_PORT% ...
echo [HAJIMI] Root: %L5_ROOT%

pushd "%L5_ROOT%"
call scripts\start_server.bat
set ERR=%ERRORLEVEL%
popd

endlocal
exit /b %ERR%
