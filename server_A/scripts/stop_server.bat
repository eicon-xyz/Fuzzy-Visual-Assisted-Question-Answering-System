@echo off
setlocal
cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010

echo [HAJIMI] Looking for process listening on port %HAJIMI_PORT% ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%HAJIMI_PORT% " ^| findstr LISTENING') do (
    echo [HAJIMI] Stopping PID %%a ...
    taskkill /PID %%a /F >nul 2>&1
)

echo [HAJIMI] If uvicorn was started with --reload, also close that terminal window.
