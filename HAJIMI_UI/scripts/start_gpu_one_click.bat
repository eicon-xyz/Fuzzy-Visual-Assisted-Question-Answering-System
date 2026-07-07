@echo off
setlocal EnableExtensions
cd /d %~dp0..

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo ============================================================
echo  HAJIMI GPU one-click: remote start.sh + tunnel + A-end + UI
echo  Password: auto via paramiko (default group2-ssh-123)
echo  Custom:  set HAJIMI_GPU_SSH_PASSWORD=your-password
echo ============================================================

"%PYTHON%" -c "import paramiko" 2>nul
if errorlevel 1 (
    echo [HAJIMI] Installing paramiko ...
    "%PYTHON%" -m pip install paramiko
    if errorlevel 1 (
        echo [HAJIMI] ERROR: pip install paramiko failed
        exit /b 1
    )
)

echo.
echo [1/4] Remote GPU: omniparser_api ./start.sh on :9800 ...
"%PYTHON%" scripts\gpu_group2_remote.py start-9800
if errorlevel 1 (
    echo [HAJIMI] Remote start failed — check campus network / GPU platform
    exit /b 1
)

echo.
echo [2/4] SSH tunnel :9800 (paramiko, no password prompt) ...
echo [HAJIMI] Clearing stale :9800 listeners ...
"%PYTHON%" scripts\kill_port.py 9800 >nul 2>&1
start "HAJIMI-GPU-Tunnel-9800" cmd /k "cd /d %~dp0.. && "%PYTHON%" scripts\gpu_tunnel_9800.py"

echo.
echo [3/4] Waiting for local :9800/health ...
set /a WAIT=0
:wait_tunnel
set /a WAIT+=1
if %WAIT% GTR 45 (
    echo [HAJIMI] TIMEOUT: tunnel not ready. Check HAJIMI-GPU-Tunnel-9800 window.
    exit /b 1
)
"%PYTHON%" scripts\check_gpu_api_tunnel.py >nul 2>&1
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_tunnel
)
echo [HAJIMI] Tunnel OK

echo.
echo [4/4] Local A-end + B-end UI ...
call "%~dp0start_gpu_api_demo.bat"
endlocal
exit /b %ERRORLEVEL%
