@echo off
setlocal EnableExtensions
cd /d %~dp0..

echo ============================================================
echo  HAJIMI local mode: local A+B + remote GPU Omni (:9800 tunnel)
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
echo [HAJIMI] Writing local gpu_api settings (127.0.0.1:8010) ...
"%PYTHON%" scripts\apply_local_gpu_settings.py
if errorlevel 1 goto fail_exit

echo.
call "%~dp0start_gpu_one_click.bat"
set ERR=%ERRORLEVEL%
endlocal
exit /b %ERR%

:fail_exit
echo [HAJIMI] Local startup preparation failed - see messages above.
pause
endlocal
exit /b 1
