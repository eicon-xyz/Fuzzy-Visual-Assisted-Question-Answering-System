@echo off
setlocal EnableExtensions
cd /d %~dp0..

echo ============================================================
echo  HAJIMI local_vision mode - no OmniParser (old :9800 stopped)
echo  L4 vision planning (DeepSeek) + L5 UIA binding + Playwright
echo ============================================================

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
timeout /t 3 /nobreak >nul

echo [HAJIMI] Starting L5 Sidecar :8011 (UIA binding execution) ...
start "HAJIMI-L5-Sidecar" cmd /k "call %~dp0start_l5_sidecar.bat"
timeout /t 2 /nobreak >nul

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
