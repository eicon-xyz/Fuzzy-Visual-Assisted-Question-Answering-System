@echo off
setlocal EnableExtensions
cd /d %~dp0

if not exist "HAJIMI_UI\scripts\ensure_desktop_env.bat" (
    echo [ERROR] missing HAJIMI_UI\scripts\ensure_desktop_env.bat
    pause
    exit /b 1
)

cd HAJIMI_UI
call scripts\ensure_desktop_env.bat
set ERR=%ERRORLEVEL%
cd ..
exit /b %ERR%
