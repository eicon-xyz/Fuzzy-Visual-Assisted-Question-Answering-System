@echo off
setlocal EnableExtensions
cd /d %~dp0

if not exist "HAJIMI_UI\scripts\start_release_fullstack.bat" (
    echo [ERROR] »±…Ÿ HAJIMI_UI\scripts\start_release_fullstack.bat
    pause
    exit /b 1
)

cd HAJIMI_UI
call scripts\start_release_fullstack.bat
set ERR=%ERRORLEVEL%
cd ..
exit /b %ERR%
