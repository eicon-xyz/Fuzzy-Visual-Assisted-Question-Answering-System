@echo off
setlocal EnableExtensions
cd /d %~dp0\..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
set HAJIMI_API_URL=http://127.0.0.1:%HAJIMI_PORT%
set HAJIMI_MOCK_FALLBACK=1

echo [HAJIMI] Mock demo ¡ª A-end without OmniParser + B UI mock fallback
call stop_all.bat
timeout /t 2 /nobreak >nul
start "HAJIMI-A-end" cmd /k "cd /d %~dp0..\.. && set HAJIMI_PORT=%HAJIMI_PORT%&& scripts\start_server.bat"
timeout /t 2 /nobreak >nul
start "HAJIMI-B-end" cmd /k "cd /d %~dp0..\.. && set HAJIMI_PORT=%HAJIMI_PORT%&& set HAJIMI_API_URL=%HAJIMI_API_URL%&& set HAJIMI_MOCK_FALLBACK=1&& scripts\start_client.bat"
endlocal
