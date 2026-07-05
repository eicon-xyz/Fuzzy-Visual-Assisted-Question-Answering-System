@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
set HAJIMI_API_URL=http://127.0.0.1:%HAJIMI_PORT%

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python
) else (
    set PYTHON=python
)

echo [HAJIMI] Step 1/2: stop stale backend on :%HAJIMI_PORT% ...
call "%~dp0stop_all.bat"

echo [HAJIMI] Step 2/2: start A-end :%HAJIMI_PORT% + B-end (no OmniParser) ...
timeout /t 2 /nobreak >nul

start "HAJIMI-A-end" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& %~dp0start_server.bat"
timeout /t 2 /nobreak >nul
start "HAJIMI-B-end" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& set HAJIMI_API_URL=%HAJIMI_API_URL%&& %~dp0start_client.bat"

echo [HAJIMI] Launched. A-end http://127.0.0.1:%HAJIMI_PORT% — pure vision LLM mode.
endlocal
