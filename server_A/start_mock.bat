@echo off
setlocal EnableExtensions
cd /d %~dp0

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
set HAJIMI_API_URL=http://127.0.0.1:%HAJIMI_PORT%

:: Enable mock fallback so B-end works without OmniParser
set HAJIMI_MOCK_FALLBACK=1

echo [HAJIMI] Starting A-end (no OmniParser) + B-end (mock fallback) ...

:: Stop stale processes
call scripts\stop_all.bat
timeout /t 2 /nobreak >nul

:: Start A-end
start "HAJIMI-A-end" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& scripts\start_server.bat"
timeout /t 2 /nobreak >nul

:: Start B-end
start "HAJIMI-B-end" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& set HAJIMI_API_URL=%HAJIMI_API_URL%&& set HAJIMI_MOCK_FALLBACK=1&& python main.py"

echo [HAJIMI] Launched. A-end: %HAJIMI_API_URL%  (Mock mode — no OmniParser)
endlocal
