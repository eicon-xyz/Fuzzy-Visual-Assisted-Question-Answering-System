@echo off
setlocal EnableExtensions
cd /d %~dp0..

if /I not "%HAJIMI_DEGRADED_START%"=="0" (
    set "HAJIMI_DEGRADED_START=1"
) else (
    set "HAJIMI_DEGRADED_START=0"
)
set "HAJIMI_START_WARN="

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo ============================================================
echo  HAJIMI GPU one-click: remote start.sh + tunnel + A-end + UI
echo  Password: auto via paramiko (default group2-ssh-123)
echo  Custom:  set HAJIMI_GPU_SSH_PASSWORD=your-password
if "%HAJIMI_DEGRADED_START%"=="1" (
    echo  Degraded: GPU/tunnel failure still launches UI ^(default^)
) else (
    echo  Strict mode: HAJIMI_DEGRADED_START=0
)
echo ============================================================

"%PYTHON%" -c "import paramiko" 2>nul
if errorlevel 1 (
    echo [HAJIMI] Installing paramiko ...
    "%PYTHON%" -m pip install paramiko
    if errorlevel 1 (
        echo [HAJIMI] ERROR: pip install paramiko failed
        goto fail_exit
    )
)

echo.
call "%~dp0ensure_hajimi_gpu_prereqs.bat"
if errorlevel 1 goto fail_exit

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
)

echo.
echo [1/5] Remote GPU: omniparser_api ./start.sh on :9800 ...
"%PYTHON%" scripts\gpu_group2_remote.py start-9800
if errorlevel 1 (
    if "%HAJIMI_DEGRADED_START%"=="1" (
        echo [HAJIMI] WARN: Remote GPU start failed — continuing degraded ^(UI will show not connected^)
        set "HAJIMI_START_WARN=1"
    ) else (
        echo [HAJIMI] Remote start failed — check campus network / GPU platform
        goto fail_exit
    )
)

echo.
echo [2/5] SSH tunnel :9800 (paramiko, no password prompt) ...
echo [HAJIMI] Clearing stale :9800 listeners ...
"%PYTHON%" scripts\kill_port.py 9800 >nul 2>&1
start "HAJIMI-GPU-Tunnel-9800" cmd /k "cd /d %~dp0.. && "%PYTHON%" scripts\gpu_tunnel_9800.py"

echo.
echo [3/5] Waiting for local :9800/health ...
set /a WAIT=0
:wait_tunnel
set /a WAIT+=1
if %WAIT% GTR 45 (
    if "%HAJIMI_DEGRADED_START%"=="1" (
        echo [HAJIMI] WARN: Tunnel not ready in 90s — continuing degraded
        set "HAJIMI_START_WARN=1"
        goto start_demo
    )
    echo [HAJIMI] TIMEOUT: tunnel not ready. Check HAJIMI-GPU-Tunnel-9800 window.
    goto fail_exit
)
"%PYTHON%" scripts\check_gpu_api_tunnel.py >nul 2>&1
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_tunnel
)
echo [HAJIMI] Tunnel OK

:start_demo
echo.
echo [4/5] Local A-end + B-end UI ...
call "%~dp0start_gpu_api_demo.bat"
set DEMO_ERR=%ERRORLEVEL%
if not "%DEMO_ERR%"=="0" set "HAJIMI_START_WARN=1"

if defined HAJIMI_START_WARN (
    echo.
    echo [HAJIMI] Startup completed with warnings — UI may show backend not connected.
    echo [HAJIMI] UI will retry every 10s. Connect campus GPU and wait, or re-run 启动HAJIMI.bat
    endlocal
    exit /b 2
)
endlocal
exit /b 0

:fail_exit
echo.
echo [HAJIMI] Startup failed — see messages above.
pause
endlocal
exit /b 1
