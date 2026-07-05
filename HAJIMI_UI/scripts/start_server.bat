@echo off
setlocal EnableExtensions

cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
if not defined HAJIMI_HOST set HAJIMI_HOST=127.0.0.1

:: Only use server\.venv — must exist
set "PYTHON=server\.venv\Scripts\python.exe"

:: If A-end is already responding to health checks, nothing to do
"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://%HAJIMI_HOST%:%HAJIMI_PORT%/api/demo/health', timeout=3)" >nul 2>&1
if not errorlevel 1 (
    echo [HAJIMI] A-end already running
    endlocal
    exit /b 0
)

echo [HAJIMI] Starting A-end on http://%HAJIMI_HOST%:%HAJIMI_PORT% ...
"%PYTHON%" -m uvicorn server.main:app --host %HAJIMI_HOST% --port %HAJIMI_PORT%

endlocal
exit /b %ERRORLEVEL%
