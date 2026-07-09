@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d %~dp0

if not exist "HAJIMI_UI\scripts\package_release.py" (
    echo [ERROR] 缺少 HAJIMI_UI\scripts\package_release.py
    pause
    exit /b 1
)

echo [HAJIMI] 正在生成 L4+L5 源码交付 zip ...
python HAJIMI_UI\scripts\package_release.py %*
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 pause
endlocal
exit /b %ERR%
