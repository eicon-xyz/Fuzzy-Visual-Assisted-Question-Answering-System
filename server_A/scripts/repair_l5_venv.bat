@echo off
setlocal EnableExtensions
cd /d %~dp0..

echo [HAJIMI-L5] Repairing L5 Sidecar venv (delete + reinstall)...
set HAJIMI_RECREATE_VENV=1
call scripts\setup_server_env.bat
set ERR=%ERRORLEVEL%
endlocal
exit /b %ERR%
