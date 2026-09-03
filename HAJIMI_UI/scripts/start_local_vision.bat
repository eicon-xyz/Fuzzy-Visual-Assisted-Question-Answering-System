@echo off
setlocal EnableExtensions

REM ============================================================
REM  HAJIMI L5 auto-execute mode launcher (no L4 guide, no :8010)
REM  ASCII-only: keep this file free of non-ASCII (GBK codepage).
REM  B-end UI + L5 Sidecar :8011 (UIA binding + Playwright DOM)
REM ============================================================

cd /d "%~dp0.." 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot cd to repo root at "%~dp0.."
    echo         UNC paths like \\wsl.localhost\... are not supported by CMD.
    echo         Please copy the repo to C:\HAJIMI and run the launcher bat from there.
    pause
    exit /b 1
)

call "%~dp0ensure_ui_env.bat"
if errorlevel 1 goto fail_exit

call "%~dp0ensure_l5_sidecar_env.bat"
if errorlevel 1 goto fail_exit

call "%~dp0_resolve_l5_root.bat"
set "PYTHON=python"
if exist "%L5_ROOT%\server\.venv\Scripts\python.exe" set "PYTHON=%L5_ROOT%\server\.venv\Scripts\python.exe"

echo.
echo [HAJIMI] Writing L5 mode settings - Sidecar :8011, no OmniParser ...
"%PYTHON%" scripts\apply_l5_settings.py
if errorlevel 1 goto fail_exit

echo.
echo [HAJIMI] Starting L5 Sidecar :8011 - UIA binding execution ...
start "HAJIMI-L5-Sidecar" cmd /k "call %~dp0start_l5_sidecar.bat"
ping -n 4 127.0.0.1 >nul 2>&1

echo [HAJIMI] Starting B-end UI ...
start "HAJIMI-B-end" cmd /k "call %~dp0start_client.bat"

echo.
echo [HAJIMI] L5 auto-execute mode launched.
echo   Exec:  UIA binding + Playwright DOM on :8011
echo   Stop:  scripts\stop_all.bat
endlocal
exit /b 0

:fail_exit
echo [HAJIMI] L5 startup preparation failed - see messages above.
pause
endlocal
exit /b 1
