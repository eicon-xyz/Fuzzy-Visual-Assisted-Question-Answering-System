@echo off
setlocal EnableExtensions

REM ============================================================
REM  HAJIMI local_vision mode - no OmniParser (old :9800 stopped)
REM  ASCII-only: keep this file free of non-ASCII (GBK codepage).
REM  L4 vision planning (DeepSeek) + L5 UIA binding + Playwright
REM ============================================================

cd /d "%~dp0.." 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot cd to repo root at "%~dp0.."
    echo         UNC paths like \\wsl.localhost\... are not supported by CMD.
    echo         Please copy the repo to C:\HAJIMI and run the launcher bat from there.
    pause
    exit /b 1
)

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

call "%~dp0ensure_ui_env.bat"
if errorlevel 1 goto fail_exit

call "%~dp0ensure_server_env.bat"
if errorlevel 1 goto fail_exit

call "%~dp0ensure_l5_sidecar_env.bat"
if errorlevel 1 goto fail_exit

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
)

echo.
echo [HAJIMI] Writing local_vision settings (deployment_mode=local_vision, routing=fast) ...
"%PYTHON%" scripts\apply_local_vision_settings.py
if errorlevel 1 goto fail_exit

echo.
echo [HAJIMI] Starting A-end :8010 (L4 vision planning) ...
start "HAJIMI-A-end" cmd /k "call %~dp0start_server.bat"
ping -n 4 127.0.0.1 >nul 2>&1

echo [HAJIMI] Starting L5 Sidecar :8011 (UIA binding execution) ...
start "HAJIMI-L5-Sidecar" cmd /k "call %~dp0start_l5_sidecar.bat"
ping -n 3 127.0.0.1 >nul 2>&1

echo [HAJIMI] Starting B-end UI ...
start "HAJIMI-B-end" cmd /k "call %~dp0start_client.bat"

echo.
echo [HAJIMI] local_vision mode launched (no OmniParser).
echo   L4 guide: DeepSeek text planning (ROUTING_MODE=fast)
echo   L5 exec:  UIA binding + Playwright DOM
echo   Stop:     scripts\stop_all.bat
endlocal
exit /b 0

:fail_exit
echo [HAJIMI] local_vision startup preparation failed - see messages above.
pause
endlocal
exit /b 1
