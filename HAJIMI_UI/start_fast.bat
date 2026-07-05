@echo off
setlocal EnableExtensions
cd /d %~dp0

set HAJIMI_PORT=8010
set HAJIMI_HOST=127.0.0.1
set HAJIMI_API_URL=http://%HAJIMI_HOST%:%HAJIMI_PORT%
set OMNI_ROOT=%~dp0OmniParser

echo [HAJIMI] Step 1/3: stop stale services ...
python scripts\kill_port.py 8002
python scripts\kill_port.py 8010
timeout /t 1 /nobreak >nul

echo [HAJIMI] Step 2/3: start OmniParser ...
start "HAJIMI-OmniParser" cmd /k "cd /d %~dp0 && set OMNI_ROOT=%OMNI_ROOT%&& scripts\start_omniparser.bat"
timeout /t 3 /nobreak >nul

echo [HAJIMI] Step 3/3: start A-end ...
start "HAJIMI-A-end" cmd /k "cd /d %~dp0 && python -m uvicorn server.main:app --host %HAJIMI_HOST% --port %HAJIMI_PORT%"
timeout /t 2 /nobreak >nul

echo [HAJIMI] Start B-end ...
start "HAJIMI-B-end" cmd /k "cd /d %~dp0 && set HAJIMI_API_URL=%HAJIMI_API_URL%&& python main.py"

echo [HAJIMI] All launched. A-end: %HAJIMI_API_URL%
endlocal
