@echo off
setlocal EnableExtensions
cd /d %~dp0

if not exist "HAJIMI_UI\scripts\start_desktop.bat" (
    echo [ERROR] missing HAJIMI_UI\scripts\start_desktop.bat
    pause
    exit /b 1
)

cd HAJIMI_UI
call scripts\start_desktop.bat
set ERR=%ERRORLEVEL%
cd ..
exit /b %ERR%
