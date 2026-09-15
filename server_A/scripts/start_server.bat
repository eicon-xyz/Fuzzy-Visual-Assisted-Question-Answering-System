@echo off
setlocal EnableExtensions

cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8011
if not defined HAJIMI_HOST set HAJIMI_HOST=127.0.0.1

set "PYTHON=server\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [HAJIMI] ERROR: L5 ^(8011^) server\.venv not found at:
    echo   %CD%\server\.venv
    echo This is NOT HAJIMI_UI\server\.venv ¡ª run: scripts\setup_server_env.bat
    exit /b 1
)

"%PYTHON%" -c "import fastapi, uvicorn, sqlalchemy, psutil" 2>nul
if errorlevel 1 (
    echo [HAJIMI] Missing L5 ^(8011^) server deps at %CD%\server\.venv
    echo Run in this folder ^(new_JIMI\HAJIMI_UI^): scripts\setup_server_env.bat
    exit /b 1
)

if exist "%~dp0kill_port.py" (
    echo [HAJIMI] Freeing port %HAJIMI_PORT% ...
    "%PYTHON%" "%~dp0kill_port.py" %HAJIMI_PORT% >nul 2>&1
)

"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://%HAJIMI_HOST%:%HAJIMI_PORT%/api/demo/health/live', timeout=3)" >nul 2>&1
if not errorlevel 1 (
    echo [HAJIMI] A-end already running on :%HAJIMI_PORT%
    endlocal
    exit /b 0
)

echo [HAJIMI] Starting A-end on http://%HAJIMI_HOST%:%HAJIMI_PORT% ...
"%PYTHON%" -m uvicorn server.main:app --host %HAJIMI_HOST% --port %HAJIMI_PORT%

endlocal
exit /b %ERRORLEVEL%
