@echo off
REM Called by setup_server_env when HAJIMI_RECREATE_VENV=1
if not defined HAJIMI_PORT set HAJIMI_PORT=8001
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%HAJIMI_PORT% " ^| findstr LISTENING 2^>nul') do (
    echo [HAJIMI] WARN: Port %HAJIMI_PORT% in use by PID %%a — run scripts\stop_server.bat first.
)
