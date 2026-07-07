@echo off
setlocal EnableExtensions
cd /d %~dp0..

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

if not defined HAJIMI_GPU_HOST set HAJIMI_GPU_HOST=10.246.2.7
if not defined HAJIMI_GPU_SSH_PORT set HAJIMI_GPU_SSH_PORT=12202
if not defined HAJIMI_GPU_USER set HAJIMI_GPU_USER=student

echo ========================================
echo  GPU OmniParser SSH tunnel (paramiko)
echo  local 9800 -^> %HAJIMI_GPU_HOST%:9800
echo  Password: auto (HAJIMI_GPU_SSH_PASSWORD or group2 default)
echo  Keep this window OPEN
echo ========================================

"%PYTHON%" -c "import paramiko" 2>nul
if errorlevel 1 (
    echo [HAJIMI] Installing paramiko ...
    "%PYTHON%" -m pip install paramiko
)

echo [HAJIMI] Clearing stale :9800 listeners ...
"%PYTHON%" scripts\kill_port.py 9800 >nul 2>&1

"%PYTHON%" scripts\gpu_tunnel_9800.py
pause
endlocal
